"""智能体请求/响应契约。

四个场景共用一个请求体：字段都是可选的，各场景取自己需要的。
这样做的好处是前端只需要一个请求模型，也不用为每个场景维护一份 schema；
代价是文档里看不出「哪些字段必填」，所以在接口描述里逐场景写清楚了。
"""
from pydantic import Field

from app.schemas.common import RequestModel


class AgentRunRequest(RequestModel):
    # 通用
    scene: str = Field(default="", max_length=24, description="路径已带场景时此字段可留空")
    conversation_id: str = Field(default="", max_length=24, description="伴读场景的多轮会话 id")

    # 匹配 / 伴读
    query: str = Field(default="", max_length=500, description="读者的自然语言需求")
    book_id: str = Field(default="", max_length=24, description="伴读时正在读的书；匹配时作为种子书")
    limit: int = Field(default=5, ge=1, le=10, description="推荐条数")

    # 录书
    raw_text: str = Field(default="", max_length=4000, description="ISBN、书名，或拍照识别出的整段文字")
    isbn: str = Field(default="", max_length=20)
    title: str = Field(default="", max_length=128)

    # 触达
    activity_id: str = Field(default="", max_length=24)
    topic: str = Field(default="", max_length=128, description="没有指定活动时的主题词")
    channel: str = Field(default="push", max_length=16, description="push / wechat / poster")

    # 伴读
    question: str = Field(default="", max_length=500, description="question 与 query 二选一")


class AgentRunOut(RequestModel):
    run_id: str = ""
    scene: str = ""
    status: str = "success"
    degraded: bool = False
    degraded_reason: str = ""
    steps: int = 0
    tokens: int = 0
    model: str = ""
    elapsed_ms: int = 0
