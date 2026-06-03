import strawberry

from internal.graph.queries import Query
from internal.graph.mutations import Mutation

schema = strawberry.Schema(query=Query, mutation=Mutation)
