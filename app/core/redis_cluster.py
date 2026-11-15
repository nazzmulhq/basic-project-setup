from typing import Annotated, Any, Protocol, cast

from fastapi import Depends
from redis.asyncio.cluster import ClusterNode, RedisCluster

from app.core.config import settings


class RedisClusterClient(Protocol):
    async def initialize(self) -> None: ...
    async def aclose(self) -> None: ...
    async def get(self, key: str) -> Any: ...
    async def getdel(self, key: str) -> Any: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> Any: ...
    async def delete(self, *keys: str) -> Any: ...


redis_cluster_client: RedisClusterClient | None = None


async def init_redis_cluster() -> RedisClusterClient:
    global redis_cluster_client
    nodes: list[ClusterNode] = []
    for node in settings.redis_cluster_nodes:
        host, separator, port = node.rpartition(":")
        if not separator or not host or not port.isdecimal():
            raise ValueError(f"Invalid Redis cluster node address: {node!r}")
        nodes.append(ClusterNode(host=host, port=int(port)))

    client_options: dict[str, Any] = {
        "startup_nodes": nodes,
        "decode_responses": True,
    }
    if settings.redis_password:
        client_options["password"] = settings.redis_password.get_secret_value()

    cluster_cls = cast(Any, RedisCluster)
    client = cluster_cls(**client_options)
    await client.initialize()
    redis_cluster_client = cast(RedisClusterClient, client)
    return redis_cluster_client


async def get_redis() -> RedisClusterClient:
    if redis_cluster_client is None:
        raise RuntimeError("Redis Cluster has not been initialized")
    return redis_cluster_client


RedisClusterDeps = Annotated[RedisClusterClient, Depends(get_redis)]
