"""
@Author         : hangu
@CreateDate     : 2026/9/4
@Description    : OpenAPI文档自定义配置，适配FastAPI factory工厂调用
"""
from dataclasses import dataclass
from logging import getLogger
from typing import Any, cast

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

_logger = getLogger(__name__)


@dataclass(slots=True)
class OpenAPICustomConfig:
    """OpenAPI自定义配置参数，方便工厂传入控制行为"""

    remove_422: bool = True
    remove_validation_error_schema: bool = True


def configure_openapi_schema(
        app: FastAPI,
        config: OpenAPICustomConfig | None = None
) -> None:
    """配置OpenAPI Schema，在FastAPI factory(create_app)中调用

    Args:
        app: FastAPI实例对象
        config: 自定义openapi配置，不传使用默认配置
    """
    cfg = config or OpenAPICustomConfig()

    def custom_openapi() -> dict[str, Any] | None:
        # OpenAPI被禁用场景，直接返回None
        if app.openapi_url is None:
            return None

        # 已经生成过schema，直接复用缓存
        if app.openapi_schema:
            return app.openapi_schema

        try:
            # 兼容低版本fastapi，过滤不存在的参数
            kwargs: dict[str, Any] = {
                'title': app.title,
                'version': app.version,
                'openapi_version': app.openapi_version,
                'summary': app.summary,
                'description': app.description,
                'routes': app.routes,
                'tags': app.openapi_tags,
                'servers': app.servers,
                'terms_of_service': app.terms_of_service,
                'contact': app.contact,
                'license_info': app.license_info,
            }
            # separate_input_output_schemas 0.95+才存在
            if hasattr(app, 'separate_input_output_schemas'):
                kwargs['separate_input_output_schemas'] = app.separate_input_output_schemas

            openapi_schema = get_openapi(**kwargs)
        except Exception:
            # 生成openapi异常，不阻断服务启动；记录完整堆栈便于排查
            _logger.exception('Generate openapi schema failed')
            return None

        components = openapi_schema.setdefault('components', {})
        schemas = components.setdefault('schemas', {})

        # 移除校验错误模型
        if cfg.remove_validation_error_schema:
            schemas.pop('ValidationError', None)
            schemas.pop('HTTPValidationError', None)

        # 移除全部接口422响应
        if cfg.remove_422:
            paths = openapi_schema.get('paths', {})
            for path_item in paths.values():
                # http method: get/post/put/delete/patch/options/head/trace
                for http_method in ('get', 'post', 'put', 'delete', 'patch', 'options', 'head', 'trace'):
                    method_obj = path_item.get(http_method)
                    if not isinstance(method_obj, dict):
                        continue
                    responses = method_obj.get('responses', {})
                    responses.pop('422', None)

        app.openapi_schema = openapi_schema
        return app.openapi_schema

    # 替换 openapi 生成函数（FastAPI 内部动态属性；cast 避免 mypy method-assign 报错）
    cast(Any, app).openapi = custom_openapi
