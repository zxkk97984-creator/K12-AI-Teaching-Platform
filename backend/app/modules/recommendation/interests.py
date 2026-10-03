"""Match explicit, currently usable interests against available course terms."""

from app.modules.memory.automatic import KeywordMemoryRetriever, terms

GENERIC_TERMS = {
    "用户",
    "学生",
    "喜欢",
    "兴趣",
    "学习",
    "希望",
    "想要",
    "相关",
    "知识",
    "内容",
    "了解",
    "关于",
    "目标",
    "计划",
    "帮助",
    "课程",
    "基础",
    "入门",
}


async def personal_interest_terms(db, *, owner_user_id, candidates):
    # Reuse retrieval's owner, active status, expiry and use-enabled boundary.
    memories = await KeywordMemoryRetriever().retrieve(
        db, owner_user_id, "我的兴趣", category="INTEREST"
    )
    catalogue_terms = set()
    for chapter in candidates:
        catalogue_terms.update(
            terms(" ".join((chapter.title, chapter.course_title, *chapter.knowledge_point_slugs)))
        )
    catalogue_terms -= GENERIC_TERMS
    matched, source_ids = set(), []
    for memory in memories:
        overlap = terms(memory["summary"]) & catalogue_terms
        if overlap:
            matched.update(overlap)
            source_ids.append(memory["id"])
    return tuple(sorted(matched)), tuple(source_ids)
