from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentDefinition(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=1000)
    role: Literal["teacher", "designer", "memory"] = "teacher"
    enabled: bool = False
    bot_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    workspace_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    prompt_version: str = Field(default="v1", max_length=80)
    remote_memory_disabled: bool = False
    capabilities: list[str] = Field(default_factory=list, max_length=40)


class RouteDefinition(StrictModel):
    operation: str = Field(min_length=1, max_length=64)
    stage: Literal["*", "PRIMARY_LOWER", "PRIMARY_UPPER", "JUNIOR", "SENIOR"] = "*"
    agent_id: str


class CapabilityDefinition(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,79}$")
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(default="1", max_length=64)
    executor: Literal["KNODO_SKILL", "BACKEND"] = "KNODO_SKILL"
    plugin_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    binding_scope: Literal["WORKSPACE", "ASSISTANT"] = "WORKSPACE"
    handler: str | None = Field(default=None, max_length=80)
    input_contract: str = Field(default="", max_length=100)
    output_contract: str = Field(default="", max_length=100)
    allowed_context: list[Literal["course", "conversation", "personal_memory"]] = Field(
        default_factory=list
    )
    enabled: bool = True


class RegistryData(StrictModel):
    agents: list[AgentDefinition] = Field(max_length=100)
    routes: list[RouteDefinition] = Field(max_length=200)
    capabilities: list[CapabilityDefinition] = Field(max_length=100)
    verifications: dict[str, dict] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def validate_links(self):
        agents = {a.id: a for a in self.agents}
        caps = {c.id for c in self.capabilities}
        if len(agents) != len(self.agents) or len(caps) != len(self.capabilities):
            raise ValueError("教师或能力标识重复")
        routes = set()
        roles = {
            "TEACH_TURN": "teacher",
            "CODE_FEEDBACK": "teacher",
            "QUIZ_DRAFT": "designer",
            "LESSON_PACKAGE_DRAFT": "designer",
            "MEMORY_EXTRACT": "memory",
        }
        for route in self.routes:
            if (route.operation, route.stage) in routes:
                raise ValueError("同一操作和学段只能配置一条默认路由")
            routes.add((route.operation, route.stage))
            if route.agent_id not in agents or not agents[route.agent_id].enabled:
                raise ValueError("路由必须指向已启用的助手")
            agent = agents[route.agent_id]
            if route.operation not in roles or agent.role != roles[route.operation]:
                raise ValueError("操作与助手职责不匹配")
            if not agent.bot_id or not agent.workspace_id:
                raise ValueError("启用路由前请填写 Bot 与工作空间 ID")
            if (
                agent.id != "legacy-tutor"
                and agent.role in ("teacher", "memory")
                and not agent.remote_memory_disabled
            ):
                raise ValueError("请先核对并关闭共享空间的远端自动记忆，再启用新路由")
        for agent in self.agents:
            if any(cap not in caps for cap in agent.capabilities):
                raise ValueError("助手关联了未登记的能力")
        return self


class RegistryUpdate(StrictModel):
    base_revision: int = Field(ge=0)
    data: RegistryData


class RegistryView(StrictModel):
    revision: int
    data: RegistryData
    persisted: bool
