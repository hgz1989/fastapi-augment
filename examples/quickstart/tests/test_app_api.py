"""
@Author         : hangu
@CreateDate     : 2026/9/23
@Description    : 示例 API 冒烟测试——CRUD + 软删除 + 聚合 + 健康检查
"""


class TestHealth:

    async def test_health(self, client) -> None:
        """健康检查：应用状态 + 数据库连通"""
        resp = await client.get('/health')
        assert resp.status_code == 200
        body = resp.json()
        assert body['status'] == 'healthy'
        names = {check['name'] for check in body['checks']}
        assert 'app' in names
        assert 'database' in names


class TestItemCrud:

    async def test_create_and_get(self, client) -> None:
        """创建商品并查询"""
        resp = await client.post('/items', json={'name': '示例商品', 'price': 9900})
        assert resp.status_code == 200
        body = resp.json()
        assert body['code'] == 0
        assert body['data']['name'] == '示例商品'
        assert body['data']['price'] == 9900
        item_id = body['data']['id']

        resp = await client.get(f'/items/{item_id}')
        assert resp.json()['data']['name'] == '示例商品'

    async def test_list_paginated(self, client) -> None:
        """分页查询"""
        for i in range(5):
            await client.post('/items', json={'name': f'item-{i}', 'price': i})
        resp = await client.get('/items', params={'page': 1, 'size': 3})
        body = resp.json()
        assert body['extra']['total'] == 5
        assert len(body['data']) == 3

    async def test_get_not_found(self, client) -> None:
        """不存在返回 404 + 统一响应格式"""
        resp = await client.get('/items/nonexistent')
        assert resp.status_code == 404
        body = resp.json()
        assert body['code'] == 404
        assert body['message'] == '商品 nonexistent 不存在'

    async def test_update(self, client) -> None:
        """更新商品"""
        created = (await client.post('/items', json={'name': '旧名', 'price': 100})).json()
        item_id = created['data']['id']
        resp = await client.put(f'/items/{item_id}', json={'name': '新名', 'price': 200})
        assert resp.status_code == 200
        assert resp.json()['data']['name'] == '新名'
        assert resp.json()['data']['price'] == 200


class TestSoftDelete:

    async def test_delete_soft_deletes(self, client) -> None:
        """删除转软删：默认查不到，include_deleted=true 可见"""
        created = (await client.post('/items', json={'name': '待删', 'price': 10})).json()
        item_id = created['data']['id']

        resp = await client.delete(f'/items/{item_id}')
        assert resp.status_code == 200

        # 默认过滤：查不到
        resp = await client.get(f'/items/{item_id}')
        assert resp.status_code == 404

        # include_deleted=true：可见且带软删标记
        resp = await client.get('/items', params={'include_deleted': 'true'})
        body = resp.json()
        assert body['extra']['total'] == 1
        assert body['data'][0]['id'] == item_id
        assert body['data'][0]['isDeleted'] is True

    async def test_list_default_excludes_deleted(self, client) -> None:
        """列表默认排除已软删行"""
        for i in range(3):
            await client.post('/items', json={'name': f'item-{i}', 'price': i})
        resp = await client.get('/items')
        item_id = resp.json()['data'][0]['id']
        await client.delete(f'/items/{item_id}')

        resp = await client.get('/items')
        assert resp.json()['extra']['total'] == 2


class TestAggregate:

    async def test_stats_excludes_deleted(self, client) -> None:
        """聚合默认排除已软删行"""
        # price: 0, 10, 20
        await client.post('/items', json={'name': 'a', 'price': 0})
        item_b = (await client.post('/items', json={'name': 'b', 'price': 10})).json()
        await client.post('/items', json={'name': 'c', 'price': 20})
        # 软删 price=10 的行
        await client.delete(f"/items/{item_b['data']['id']}")

        resp = await client.get('/items/stats/total')
        body = resp.json()
        assert body['data']['total_price'] == 20
        assert body['data']['avg_price'] == 10
