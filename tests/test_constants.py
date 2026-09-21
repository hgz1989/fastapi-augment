"""
common.constants 模块测试
"""
from starlette import status

from fastapi_augment.common.constants import (
    DEFAULT_ERR_MSG
)


class TestDefaultErrMsg:

    def test_contains_all_common_codes(self):
        expected_codes = [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_402_PAYMENT_REQUIRED,
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_405_METHOD_NOT_ALLOWED,
            status.HTTP_406_NOT_ACCEPTABLE,
            status.HTTP_408_REQUEST_TIMEOUT,
            status.HTTP_409_CONFLICT,
            status.HTTP_410_GONE,
            status.HTTP_412_PRECONDITION_FAILED,
            status.HTTP_413_CONTENT_TOO_LARGE,
            status.HTTP_414_URI_TOO_LONG,
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            status.HTTP_423_LOCKED,
            status.HTTP_429_TOO_MANY_REQUESTS,
        ]
        for code in expected_codes:
            assert code in DEFAULT_ERR_MSG, f'Missing status code {code}'

    def test_values_are_strings(self):
        for code, msg in DEFAULT_ERR_MSG.items():
            assert isinstance(msg, str), f'Code {code} has non-string message'
            assert len(msg) > 0, f'Code {code} has empty message'

    def test_all_4xx_range(self):
        """所有键都在 4xx 范围"""
        for code in DEFAULT_ERR_MSG:
            assert 400 <= code < 500, f'Code {code} is not in 4xx range'
