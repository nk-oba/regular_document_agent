"""
PKCEHandler ユニットテスト
PKCE機能のテストケース
"""

import pytest
import secrets
from agents.mcp_client.auth.pkce_handler import PKCEHandler


class TestPKCEHandler:
    """PKCEHandlerのテストクラス"""
    
    def test_pkce_params_generation(self):
        """PKCE パラメータ生成のテスト"""
        handler = PKCEHandler()
        
        code_verifier, code_challenge, state = handler.generate_pkce_params()
        
        # パラメータが生成されていることを確認
        assert code_verifier is not None
        assert code_challenge is not None
        assert state is not None
        
        # 長さのチェック
        assert len(code_verifier) > 43  # RFC 7636: minimum 43 characters
        assert len(code_challenge) > 0
        assert len(state) > 0
    
    def test_code_verifier_format(self):
        """code_verifier フォーマットのテスト"""
        handler = PKCEHandler()
        code_verifier, _, _ = handler.generate_pkce_params()
        
        # Base64URL文字のみ含まれることを確認
        import re
        assert re.match(r'^[A-Za-z0-9_-]+$', code_verifier)
    
    def test_code_challenge_generation(self):
        """code_challenge 生成のテスト"""
        import hashlib
        import base64
        
        handler = PKCEHandler()
        code_verifier, code_challenge, _ = handler.generate_pkce_params()
        
        # 手動でcode_challengeを計算
        expected_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        assert code_challenge == expected_challenge
    
    def test_state_validation_success(self):
        """state パラメータ検証成功のテスト"""
        handler = PKCEHandler()
        _, _, state = handler.generate_pkce_params()
        
        # 同じstateで検証
        assert handler.validate_state(state) is True
    
    def test_state_validation_failure(self):
        """state パラメータ検証失敗のテスト"""
        handler = PKCEHandler()
        handler.generate_pkce_params()
        
        # 異なるstateで検証
        fake_state = "fake_state_value"
        assert handler.validate_state(fake_state) is False
    
    def test_state_validation_no_state(self):
        """state未生成時の検証テスト"""
        handler = PKCEHandler()
        
        # stateが生成されていない状態で検証
        assert handler.validate_state("any_state") is False
    
    def test_getters(self):
        """ゲッターメソッドのテスト"""
        handler = PKCEHandler()
        
        # 生成前は全てNone
        assert handler.get_code_verifier() is None
        assert handler.get_code_challenge() is None
        assert handler.get_state() is None
        
        # 生成後は値が取得できる
        code_verifier, code_challenge, state = handler.generate_pkce_params()
        
        assert handler.get_code_verifier() == code_verifier
        assert handler.get_code_challenge() == code_challenge
        assert handler.get_state() == state
    
    def test_clear(self):
        """クリア機能のテスト"""
        handler = PKCEHandler()
        handler.generate_pkce_params()
        
        # クリア前は値が存在
        assert handler.get_code_verifier() is not None
        assert handler.get_code_challenge() is not None
        assert handler.get_state() is not None
        
        # クリア後は全てNone
        handler.clear()
        assert handler.get_code_verifier() is None
        assert handler.get_code_challenge() is None
        assert handler.get_state() is None
    
    def test_is_ready(self):
        """準備状態チェックのテスト"""
        handler = PKCEHandler()
        
        # 初期状態では準備未完了
        assert handler.is_ready() is False
        
        # パラメータ生成後は準備完了
        handler.generate_pkce_params()
        assert handler.is_ready() is True
        
        # クリア後は準備未完了
        handler.clear()
        assert handler.is_ready() is False
    
    def test_code_challenge_method(self):
        """code_challenge_method のテスト"""
        assert PKCEHandler.verify_code_challenge_method() == 'S256'
    
    def test_multiple_generations(self):
        """複数回生成のテスト"""
        handler = PKCEHandler()
        
        # 1回目の生成
        cv1, cc1, s1 = handler.generate_pkce_params()
        
        # 2回目の生成
        cv2, cc2, s2 = handler.generate_pkce_params()
        
        # 値が異なることを確認（ランダム性のテスト）
        assert cv1 != cv2
        assert cc1 != cc2
        assert s1 != s2
        
        # 最新の値が保存されていることを確認
        assert handler.get_code_verifier() == cv2
        assert handler.get_code_challenge() == cc2
        assert handler.get_state() == s2
    
    def test_string_representation(self):
        """文字列表現のテスト"""
        handler = PKCEHandler()
        
        # 初期状態
        str_repr = str(handler)
        assert "PKCEHandler" in str_repr
        assert "None" in str_repr
        
        # パラメータ生成後
        handler.generate_pkce_params()
        str_repr = str(handler)
        assert "PKCEHandler" in str_repr
        assert "***" in str_repr  # code_verifierはマスクされる
        assert "..." in str_repr   # その他の値は短縮される
    
    def test_parameter_uniqueness(self):
        """パラメータのユニーク性テスト"""
        # 複数のハンドラーで生成される値がユニークであることを確認
        handlers = [PKCEHandler() for _ in range(10)]
        params = [handler.generate_pkce_params() for handler in handlers]
        
        # 全ての code_verifier が異なることを確認
        code_verifiers = [param[0] for param in params]
        assert len(set(code_verifiers)) == len(code_verifiers)
        
        # 全ての code_challenge が異なることを確認
        code_challenges = [param[1] for param in params]
        assert len(set(code_challenges)) == len(code_challenges)
        
        # 全ての state が異なることを確認
        states = [param[2] for param in params]
        assert len(set(states)) == len(states)


if __name__ == '__main__':
    pytest.main([__file__])