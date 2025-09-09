"""
Artifact Service Module
Handles all artifact-related operations including loading, processing, and streaming.
"""
import logging
from typing import Optional, Tuple, List, Dict, Any
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from config import AppConfig
from app_utils import get_mime_type_from_extension, prepare_file_data, get_db_connection
from error_handlers import handle_artifact_error

logger = logging.getLogger(__name__)

class ArtifactService:
    """Service class for handling artifact operations."""
    
    def __init__(self):
        self.gcs_bucket_name = AppConfig.get_gcs_bucket_name()
        
    async def load_artifact_with_fallback(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        artifact_name: str,
        version: Optional[int] = None
    ) -> Tuple[Any, List[str]]:
        """
        Load artifact with multiple fallback patterns.
        
        Returns:
            Tuple of (artifact, attempted_paths)
        """
        from google.adk.artifacts import GcsArtifactService
        
        gcs_service = GcsArtifactService(bucket_name=self.gcs_bucket_name)
        artifact = None
        attempted_paths = []
        
        # Pattern 1: Use provided parameters as-is
        artifact = await self._try_load_pattern_1(
            gcs_service, app_name, user_id, session_id, artifact_name, version, attempted_paths
        )
        
        # Pattern 2: Handle unknown session_id
        if not artifact and session_id == "unknown":
            artifact = await self._try_load_pattern_2(
                gcs_service, app_name, user_id, artifact_name, version, attempted_paths
            )
        
        # Pattern 3: Handle test user_id
        if not artifact and user_id == "test":
            artifact = await self._try_load_pattern_3(
                gcs_service, app_name, artifact_name, version, attempted_paths
            )
        
        return artifact, attempted_paths
    
    async def _try_load_pattern_1(
        self,
        gcs_service,
        app_name: str,
        user_id: str,
        session_id: str,
        artifact_name: str,
        version: Optional[int],
        attempted_paths: List[str]
    ) -> Any:
        """Try loading with provided parameters."""
        try:
            logger.info(f"Trying pattern 1: app={app_name}, user={user_id}, session={session_id}")
            
            if version is not None:
                artifact = await gcs_service.load_artifact(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id,
                    filename=artifact_name,
                    version=version
                )
            else:
                artifact = await gcs_service.load_artifact(
                    app_name=app_name,
                    user_id=user_id,
                    session_id=session_id,
                    filename=artifact_name
                )
            
            attempted_paths.append(f"{app_name}/{user_id}/{session_id}/{artifact_name}")
            if artifact:
                logger.info("Found artifact with pattern 1")
            return artifact
            
        except Exception as e:
            logger.warning(f"Pattern 1 failed: {e}")
            return None
    
    async def _try_load_pattern_2(
        self,
        gcs_service,
        app_name: str,
        user_id: str,
        artifact_name: str,
        version: Optional[int],
        attempted_paths: List[str]
    ) -> Any:
        """Try loading with latest session for user."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id FROM sessions 
                    WHERE user_id = ? AND app_name = ?
                    ORDER BY update_time DESC 
                    LIMIT 1
                """, (user_id, app_name))
                
                result = cursor.fetchone()
                if result:
                    actual_session_id = result[0]
                    logger.info(f"Trying pattern 2 with actual session: {actual_session_id}")
                    
                    if version is not None:
                        artifact = await gcs_service.load_artifact(
                            app_name=app_name,
                            user_id=user_id,
                            session_id=actual_session_id,
                            filename=artifact_name,
                            version=version
                        )
                    else:
                        artifact = await gcs_service.load_artifact(
                            app_name=app_name,
                            user_id=user_id,
                            session_id=actual_session_id,
                            filename=artifact_name
                        )
                    
                    attempted_paths.append(f"{app_name}/{user_id}/{actual_session_id}/{artifact_name}")
                    if artifact:
                        logger.info(f"Found artifact with pattern 2 (session: {actual_session_id})")
                        return artifact
                        
        except Exception as e:
            logger.warning(f"Pattern 2 failed: {e}")
        
        return None
    
    async def _try_load_pattern_3(
        self,
        gcs_service,
        app_name: str,
        artifact_name: str,
        version: Optional[int],
        attempted_paths: List[str]
    ) -> Any:
        """Try loading with recent active users."""
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT user_id, id FROM sessions 
                    WHERE app_name = ?
                    ORDER BY update_time DESC 
                    LIMIT 5
                """, (app_name,))
                
                results = cursor.fetchall()
                for db_user_id, db_session_id in results:
                    try:
                        logger.info(f"Trying pattern 3 with user={db_user_id}, session={db_session_id}")
                        
                        if version is not None:
                            artifact = await gcs_service.load_artifact(
                                app_name=app_name,
                                user_id=db_user_id,
                                session_id=db_session_id,
                                filename=artifact_name,
                                version=version
                            )
                        else:
                            artifact = await gcs_service.load_artifact(
                                app_name=app_name,
                                user_id=db_user_id,
                                session_id=db_session_id,
                                filename=artifact_name
                            )
                        
                        attempted_paths.append(f"{app_name}/{db_user_id}/{db_session_id}/{artifact_name}")
                        if artifact:
                            logger.info(f"Found artifact with pattern 3 (user={db_user_id})")
                            return artifact
                            
                    except Exception as e:
                        logger.debug(f"Pattern 3 attempt failed for user={db_user_id}: {e}")
                        
        except Exception as e:
            logger.warning(f"Pattern 3 failed: {e}")
        
        return None
    
    def extract_file_data_and_mime_type(self, artifact, artifact_name: str) -> Tuple[bytes, str]:
        """Extract file data and determine MIME type from artifact."""
        file_data = None
        mime_type = "application/octet-stream"
        
        # Extract file data from artifact
        if artifact and hasattr(artifact, 'inline_data') and artifact.inline_data:
            file_data = artifact.inline_data.data
            if hasattr(artifact.inline_data, 'mime_type') and artifact.inline_data.mime_type:
                mime_type = artifact.inline_data.mime_type
        elif hasattr(artifact, 'data'):
            file_data = artifact.data
        else:
            raise HTTPException(status_code=500, detail="Unable to extract file data from artifact")
        
        # Validate and prepare file data
        file_data = prepare_file_data(file_data)
        
        # Determine MIME type from filename if not set
        if mime_type == "application/octet-stream":
            mime_type = get_mime_type_from_extension(artifact_name)
        
        return file_data, mime_type
    
    def create_streaming_response(
        self, 
        file_data: bytes, 
        artifact_name: str, 
        mime_type: str
    ) -> StreamingResponse:
        """Create a streaming response for file download."""
        def generate():
            yield file_data
        
        logger.info(f"Streaming artifact: {artifact_name} (size: {len(file_data)} bytes, mime_type: {mime_type})")
        
        return StreamingResponse(
            generate(),
            media_type=mime_type,
            headers={
                "Content-Disposition": f"attachment; filename=\"{artifact_name}\"",
                "Content-Length": str(len(file_data)),
                "Cache-Control": "no-cache"
            }
        )
    
    async def download_artifact(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
        artifact_name: str,
        version: Optional[int] = None
    ) -> StreamingResponse:
        """
        Main method for downloading artifacts with fallback patterns.
        
        Args:
            app_name: Application name
            user_id: User ID
            session_id: Session ID
            artifact_name: Name of the artifact file
            version: Optional version number
            
        Returns:
            StreamingResponse for file download
            
        Raises:
            HTTPException: If artifact not found or processing fails
        """
        try:
            logger.info(f"Download request: app={app_name}, user={user_id}, session={session_id}, file={artifact_name}, version={version}")
            
            # Try to load artifact with fallback patterns
            artifact, attempted_paths = await self.load_artifact_with_fallback(
                app_name, user_id, session_id, artifact_name, version
            )
            
            if not artifact:
                logger.error(f"Artifact not found after trying all patterns. Attempted: {attempted_paths}")
                raise HTTPException(
                    status_code=404, 
                    detail=f"Artifact not found: {artifact_name}. Tried paths: {attempted_paths}"
                )
            
            # Extract file data and determine MIME type
            file_data, mime_type = self.extract_file_data_and_mime_type(artifact, artifact_name)
            
            # Create and return streaming response
            return self.create_streaming_response(file_data, artifact_name, mime_type)
            
        except HTTPException:
            # Re-raise HTTP exceptions as-is
            raise
        except Exception as e:
            logger.error(f"Failed to download artifact: {e}")
            import traceback
            traceback.print_exc()
            raise handle_artifact_error(e, "download", artifact_name)

class InvocationArtifactService:
    """Service for handling artifacts by invocation ID."""
    
    def __init__(self):
        self.artifact_service = ArtifactService()
        
    async def get_user_candidates(self, app_name: str) -> List[str]:
        """Get list of potential user IDs from recent sessions."""
        from app_utils import generate_adk_user_id
        
        user_candidates = []
        
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT DISTINCT user_id FROM sessions 
                    WHERE app_name = ? 
                    ORDER BY update_time DESC 
                    LIMIT 20
                """, (app_name,))
                
                recent_users = [row[0] for row in cursor.fetchall()]
                
                # Convert email format users to ADK stable user IDs
                for user_id in recent_users:
                    if isinstance(user_id, str) and '@' in user_id:
                        # Email format - convert to ADK user ID
                        adk_user_id = generate_adk_user_id(user_id)
                        user_candidates.append(adk_user_id)
                        # Also keep original for backward compatibility
                        user_candidates.append(user_id)
                    else:
                        user_candidates.append(user_id)
                        
        except Exception as db_error:
            logger.warning(f"Failed to get recent users from database: {db_error}")
        
        # Add fallback patterns
        user_candidates.extend(["anonymous", "test_user"])
        
        # Remove duplicates while preserving order
        return list(dict.fromkeys(user_candidates))
    
    async def download_artifact_by_invocation(
        self,
        invocation_id: str,
        artifact_name: str,
        version: Optional[int] = None
    ) -> StreamingResponse:
        """
        Download artifact using invocation ID as session ID.
        
        Args:
            invocation_id: Invocation ID (used as session ID)
            artifact_name: Name of the artifact file
            version: Optional version number
            
        Returns:
            StreamingResponse for file download
            
        Raises:
            HTTPException: If artifact not found or processing fails
        """
        try:
            logger.info(f"Download by invocation: {invocation_id}, file: {artifact_name}")
            
            app_name = "document_creating_agent"  # Fixed app name
            user_candidates = await self.get_user_candidates(app_name)
            
            # Try each user candidate with invocation_id as session_id
            for candidate_user_id in user_candidates:
                try:
                    artifact, _ = await self.artifact_service.load_artifact_with_fallback(
                        app_name, candidate_user_id, invocation_id, artifact_name, version
                    )
                    
                    if artifact:
                        logger.info(f"Found artifact using user_id={candidate_user_id}, session_id={invocation_id}")
                        
                        # Extract file data and create response
                        file_data, mime_type = self.artifact_service.extract_file_data_and_mime_type(
                            artifact, artifact_name
                        )
                        
                        return self.artifact_service.create_streaming_response(
                            file_data, artifact_name, mime_type
                        )
                        
                except Exception as search_error:
                    logger.debug(f"Search failed for user_id={candidate_user_id}: {search_error}")
                    continue
            
            # If not found with invocation as session, try other patterns
            logger.warning(f"Artifact not found with invocation_id as session_id: {invocation_id}")
            raise HTTPException(
                status_code=404, 
                detail=f"Artifact not found: {artifact_name} for invocation {invocation_id}"
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Failed to download artifact by invocation: {e}")
            import traceback
            traceback.print_exc()
            raise handle_artifact_error(e, "download by invocation", artifact_name)