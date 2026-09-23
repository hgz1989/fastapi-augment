"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 示例业务路由——RepositoryBase CRUD + 软删除 + 聚合
"""
from fastapi import APIRouter, Depends
from fastapi_augment.common.exceptions import NotFoundError
from fastapi_augment.db.sqlalchemy import RepositoryBase, SessionFactory
from fastapi_augment.schemas import (
    PageParams,
    response_success,
)
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models import Item
from apps.api.schemas import ItemCreate, ItemOut


def build_router(sessions: SessionFactory) -> APIRouter:
    """构建商品路由

    采用工厂函数而非模块级单例：会话工厂由调用方注入，
    便于测试时替换为内存数据库实例。

    Args:
        sessions: 会话工厂（读写分离、FastAPI Depends 注入）

    Returns:
        商品路由
    """
    router = APIRouter(prefix='/items', tags=['items'])
    item_repo = RepositoryBase(Item)

    @router.post('')
    async def create_item(
            req: ItemCreate,
            session: AsyncSession = Depends(sessions.depends_transaction),
    ):
        """创建商品"""
        item = await item_repo.create(session, Item(name=req.name, price=req.price))
        return response_success(data=ItemOut.model_validate(item))

    @router.get('')
    async def list_items(
            params: PageParams = Depends(),
            include_deleted: bool = False,
            session: AsyncSession = Depends(sessions.depends_read),
    ):
        """分页查询商品（软删模型默认排除已删除行）"""
        result = await item_repo.paginate(
            session,
            page=params.page,
            size=params.size,
            include_deleted=include_deleted,
            order_by=['-created_at'],
        )
        return response_success(
            data=[ItemOut.model_validate(item) for item in result['items']],
            extra={
                'page': result['page'],
                'size': result['size'],
                'total': result['total'],
                'pages': result['pages'],
            },
        )

    @router.get('/stats/total')
    async def item_stats(
            session: AsyncSession = Depends(sessions.depends_read),
    ):
        """聚合示例：总价与均价（软删模型默认排除已删除行）"""
        return response_success(data={
            'total_price': await item_repo.sum(session, 'price'),
            'avg_price': await item_repo.avg(session, 'price'),
        })

    @router.get('/{item_id}')
    async def get_item(
            item_id: str,
            session: AsyncSession = Depends(sessions.depends_read),
    ):
        """查询单个商品"""
        item = await item_repo.get(session, item_id)
        if item is None:
            raise NotFoundError(detail=f'商品 {item_id} 不存在')
        return response_success(data=ItemOut.model_validate(item))

    @router.put('/{item_id}')
    async def update_item(
            item_id: str,
            req: ItemCreate,
            session: AsyncSession = Depends(sessions.depends_transaction),
    ):
        """更新商品"""
        affected = await item_repo.update_by_id(
            session, item_id, name=req.name, price=req.price
        )
        if not affected:
            raise NotFoundError(detail=f'商品 {item_id} 不存在')
        item = await item_repo.get(session, item_id)
        return response_success(data=ItemOut.model_validate(item))

    @router.delete('/{item_id}')
    async def delete_item(
            item_id: str,
            session: AsyncSession = Depends(sessions.depends_transaction),
    ):
        """删除商品（软删模型自动转软删，不会物理删除）"""
        deleted = await item_repo.delete_by_id(session, item_id)
        if not deleted:
            raise NotFoundError(detail=f'商品 {item_id} 不存在')
        return response_success()

    return router
