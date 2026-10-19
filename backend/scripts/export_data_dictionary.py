"""导出数据字典与「脱敏数据申请清单」。

产出两个文件：
    docs/数据字典.md                       —— 仓库内可读的完整数据字典
    docs/数据字段清单-脱敏数据申请.xlsx     —— 交给图书馆/教务老师的申请表

字段从 ORM 模型（app/db/models.py）实时读取，中文名/是否申请/脱敏方式/用途
来自下面的元数据表，保证「代码改了文档跟着改」，不会出现两边对不上。

用法： python scripts/export_data_dictionary.py
"""
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter  # noqa: E402

from app.db.base import Base  # noqa: E402
from app.db import models  # noqa: E402,F401  注册模型

DOCS_DIR = BACKEND_DIR.parent / "docs"

TABLE_CN = {
    "users": ("用户", "账号主体与学生基本信息"),
    "activities": ("阅读推广活动", "活动全生命周期，含审批与定级"),
    "activity_signups": ("活动报名", "报名与签到记录"),
    "books": ("图书", "书目元数据与馆藏信息"),
    "borrow_records": ("借阅记录", "谁在什么时候借了什么书（AI 匹配 / 触达的核心）"),
    "book_favorites": ("收藏与评分", "显式偏好，推荐信噪比最高的一类信号"),
    "reading_events": ("阅读行为", "检索、浏览、AI 互动、报名、读推送等埋点"),
    "drift_records": ("图书漂流", "单册漂流的持有者与流转记录"),
    "certificates": ("电子证书", "证书编号、验真码与颁发信息"),
    "activity_summaries": ("活动总结", "活动结束后的回顾文章与照片"),
    "notifications": ("站内推送", "按角色分发的通知"),
    "ai_conversations": ("AI 会话", "伴读、推荐、文案生成的对话记录"),
    "permission_logs": ("权限审计", "谁改了谁的权限"),
}

# (表, 字段) -> (中文名, 是否申请, 脱敏方式, 用途, 示例)
# 是否申请：是 / 可选 / 否（否 = 系统自建或不涉及学校数据）
META = {
    ("users", "user_id"): ("用户主键", "否", "—", "内部标识，由系统生成", "usr_9f2a1c77b0d4"),
    ("users", "student_no"): ("学号（脱敏）", "是", "R1 加盐哈希后取 16 位", "唯一标识学生，用于关联借阅与活动", "u_7c1f9a2e5b3d08a4"),
    ("users", "name"): ("姓名", "否", "R2 不导出（或张*）", "仅证书显示，可由系统内填报", "张*"),
    ("users", "role"): ("角色", "否", "—", "权限体系字段，系统内维护", "student"),
    ("users", "college"): ("学院", "是", "—", "推荐与活动推送的分群维度", "计算机学院"),
    ("users", "major"): ("专业", "是", "—", "推荐冷启动的学科偏好", "计算机科学与技术"),
    ("users", "class_no"): ("班级", "可选", "—", "可选分群维度", "2025211801"),
    ("users", "grade"): ("年级", "是", "—", "区分新生/毕业班的推荐策略", "2025"),
    ("users", "phone"): ("手机号", "否", "R6 不申请", "涉及个人信息，本项目不需要", "177****3115"),
    ("users", "email"): ("邮箱", "否", "R6 不申请", "涉及个人信息，本项目不需要", "21****@bupt.edu.cn"),
    ("users", "avatar_url"): ("头像", "否", "R6 不申请", "不参与推荐", ""),
    ("users", "status"): ("账号状态", "可选", "—", "判断在读/离校，用于剔除无效样本", "active"),
    ("users", "granted_permissions"): ("额外授予权限", "否", "—", "权限体系，系统内维护", "[]"),
    ("users", "revoked_permissions"): ("已收回权限", "否", "—", "权限体系，系统内维护", "[]"),
    ("users", "last_login_at"): ("最后登录时间", "否", "—", "本系统内产生", "2026-10-18T21:12:00+08:00"),
    ("users", "created_at"): ("创建时间", "否", "—", "通用字段", "2026-09-01T10:00:00+08:00"),
    ("users", "updated_at"): ("更新时间", "否", "—", "通用字段", "2026-10-18T21:12:00+08:00"),
    ("users", "is_deleted"): ("是否删除", "否", "—", "通用字段", "0"),
    # ---------------- 借阅记录（本次申请的核心） ----------------
    ("borrow_records", "borrow_id"): ("借阅流水号", "否", "—", "内部标识，由导入时生成", "brw_2a91f0c3de77"),
    ("borrow_records", "user_id"): ("读者（脱敏）", "是", "R1 加盐哈希后取 16 位", "关联读者的借阅历史", "u_7c1f9a2e5b3d08a4"),
    ("borrow_records", "book_id"): ("图书主键", "否", "—", "导入时按 ISBN 匹配生成", "bok_5c83b1e70a2d"),
    ("borrow_records", "isbn"): ("ISBN", "是", "—", "借阅与书目的关联键，非个人信息", "9787115428028"),
    ("borrow_records", "lib_barcode"): ("馆藏条码", "可选", "R4 可截断末 4 位", "区分同一书目的不同复本", "B2023-004512"),
    ("borrow_records", "borrowed_at"): ("借出日期", "是", "R3 保留到日", "构建借阅时序，做序列推荐", "2026-03-12"),
    ("borrow_records", "due_at"): ("应还日期", "是", "R3 保留到日", "计算借阅时长", "2026-04-11"),
    ("borrow_records", "returned_at"): ("归还日期", "是", "R3 保留到日", "行为序列的结束点", "2026-04-08"),
    ("borrow_records", "renew_count"): ("续借次数", "是", "—", "衡量真实兴趣强度", "1"),
    ("borrow_records", "status"): ("借阅状态", "是", "—", "在借/已还/逾期", "returned"),
    ("borrow_records", "source"): ("来源", "否", "—", "本系统扩展（漂流/荐购）", "library"),
    ("borrow_records", "created_at"): ("创建时间", "否", "—", "通用字段", "2026-03-12T09:00:00+08:00"),
    ("borrow_records", "updated_at"): ("更新时间", "否", "—", "通用字段", "2026-04-08T16:30:00+08:00"),
    ("borrow_records", "is_deleted"): ("是否删除", "否", "—", "通用字段", "0"),
    # ---------------- 书目 ----------------
    ("books", "isbn"): ("ISBN", "是", "—", "书目唯一标识", "9787115428028"),
    ("books", "title"): ("书名", "是", "—", "推荐结果展示", "深度学习"),
    ("books", "author"): ("作者", "是", "—", "推荐解释与相似度", "Ian Goodfellow"),
    ("books", "publisher"): ("出版社", "是", "—", "推荐解释", "人民邮电出版社"),
    ("books", "publish_date"): ("出版年", "是", "—", "新书推荐与时效过滤", "2017"),
    ("books", "clc_code"): ("中图法分类号", "是", "—", "学科归类的权威依据", "TP181"),
    ("books", "call_no"): ("索书号", "是", "—", "馆藏定位与同类书推荐", "TP181/GL2"),
    ("books", "pages"): ("页数", "可选", "—", "阅读时长预估", "652"),
    ("books", "price"): ("定价", "可选", "—", "荐购与预算参考", "168.00"),
    ("books", "toc"): ("目录", "可选", "—", "AI 伴读生成导读", "第 1 章 引言……"),
    ("books", "lib_location"): ("馆藏地", "是", "—", "「去图书馆找这本书」", "沙河校区三层 A 区"),
    ("books", "total_copies"): ("馆藏复本数", "是", "—", "热门度与可得性", "4"),
    ("books", "available_copies"): ("可借复本数", "是", "—", "推荐时过滤借不到的书", "2"),
    ("books", "borrow_count"): ("历史借阅次数", "是", "—", "热度基线，解决冷启动", "37"),
    ("books", "summary"): ("内容简介", "可选", "—", "推荐理由生成素材", "本书系统讲解……"),
    ("books", "category"): ("分类", "可选", "—", "粗粒度分类", "计算机"),
}

MASK_RULES = [
    ("R1", "学号 / 读者号", "加盐 HMAC-SHA256 后取前 16 位；盐值由校方或项目组保管，不随数据导出",
     "2025211995", "u_7c1f9a2e5b3d08a4", "同一学生在多次导出中保持一致，可跨表关联，但无法反推学号"),
    ("R2", "姓名", "不导出；如确需，保留姓氏 + 星号",
     "万贝", "万*", "证书展示所需姓名由系统内自行填报，不依赖校方数据"),
    ("R3", "日期时间", "统一截断到「日」，去掉时分秒；时区统一 +08:00",
     "2026-03-12 09:41:22", "2026-03-12", "推荐只需要日粒度序列，精确到秒无必要"),
    ("R4", "馆藏条码", "如需可截断末 4 位，保留前缀以便区分复本",
     "B2023-004512", "B2023-0045**", "条码本身不含个人信息，可按需保留"),
    ("R5", "借阅金额 / 罚款", "不申请", "—", "—", "涉及财务信息，与推荐目标无关"),
    ("R6", "手机号 / 邮箱 / 身份证 / 成绩 / 家庭住址 / 生源地", "不申请", "—", "—",
     "与阅读推广目标无关，遵循最小必要原则"),
]

NOT_REQUESTED = [
    ("手机号、邮箱", "个人信息，推送走站内消息即可，不需外部联系方式"),
    ("身份证号、照片", "敏感个人信息，与业务目标无关"),
    ("成绩、绩点、奖惩记录", "与阅读推广无关，且可能造成不当关联"),
    ("借阅罚款金额、欠款状态", "财务信息，推荐场景不需要"),
    ("家庭住址、生源地", "敏感个人信息，最小必要原则下不采集"),
    ("实时定位、设备信息", "不在本项目采集范围"),
]

ESTIMATE = [
    ("users（在读学生）", "约 2 万行", "只需学院/专业/年级/班级 + 学号哈希"),
    ("books（书目）", "约 10 万行", "馆藏书目全量，不含个人信息"),
    ("borrow_records（借阅记录）", "约 50 万行 / 2 学年", "可按学期分批导出，CSV 即可"),
    ("reading_events（行为埋点）", "系统自建，无需申请", "本项目上线后自行积累"),
    ("activities / activity_signups", "系统自建，无需申请", "本项目上线后自行积累"),
]


# 通用字段的中文名（未在 META 中单独列出的字段用这张表兜底）
COMMON_CN = {
    "created_at": "创建时间",
    "updated_at": "更新时间",
    "is_deleted": "是否删除",
    "status": "状态",
    "title": "标题",
    "summary": "简介",
    "content": "正文",
    "cover_url": "封面图",
    "location": "地点",
    "category": "分类",
    "level": "等级",
    "start_at": "开始时间",
    "end_at": "结束时间",
    "capacity": "名额",
    "signup_count": "报名人数",
    "checkin_count": "签到人数",
}


def cn_of(table: str, column: str, fallback: str) -> tuple[str, str, str, str, str]:
    hit = META.get((table, column))
    if hit:
        return hit
    return (COMMON_CN.get(column, "—"), "否", "—", "系统内部字段", "")


def type_of(column) -> str:
    try:
        name = column.type.python_type.__name__
    except NotImplementedError:
        name = str(column.type)
    return {
        "str": "string",
        "int": "int",
        "float": "decimal",
        "bool": "bool",
        "datetime": "datetime",
        "list": "json",
        "dict": "json",
    }.get(name, name)


def collect_rows() -> list[dict]:
    rows: list[dict] = []
    index = 0
    for table in Base.metadata.sorted_tables:
        table_cn, table_desc = TABLE_CN.get(table.name, (table.name, ""))
        for column in table.columns:
            index += 1
            cn, apply_flag, mask, usage, example = cn_of(table.name, column.name, column.name)
            rows.append(
                {
                    "no": index,
                    "table": table.name,
                    "table_cn": table_cn,
                    "table_desc": table_desc,
                    "column": column.name,
                    "cn": cn,
                    "type": type_of(column),
                    "required": "是" if not column.nullable else "否",
                    "apply": apply_flag,
                    "mask": mask,
                    "usage": usage,
                    "example": example,
                }
            )
    return rows


HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
THIN = Side(style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
APPLY_FILL = {
    "是": PatternFill("solid", fgColor="E2EFDA"),
    "可选": PatternFill("solid", fgColor="FFF2CC"),
    "否": PatternFill("solid", fgColor="F2F2F2"),
}


def style_header(ws, row: int = 1) -> None:
    for cell in ws[row]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.freeze_panes = f"A{row + 1}"
    ws.row_dimensions[row].height = 30


def autosize(ws, widths: dict[str, int]) -> None:
    for letter, width in widths.items():
        ws.column_dimensions[letter].width = width


def build_workbook(rows: list[dict]) -> Workbook:
    wb = Workbook()

    # ---------------- Sheet 1 申请说明 ----------------
    ws = wb.active
    ws.title = "① 申请说明"
    ws["A1"] = "「智阅校园」阅读推广平台 · 脱敏数据申请说明"
    ws["A1"].font = Font(size=16, bold=True, color="1F4E79")
    ws.merge_cells("A1:D1")

    intro = [
        ("一、申请方", "北京邮电大学「智阅校园」大学生创新创业训练计划项目组"),
        ("二、数据用途", "构建校园阅读推广平台的推荐与导读能力，仅用于本项目研究与校内服务，"
                        "不对外提供、不用于商业目的、不做个体画像的商业化输出"),
        ("三、申请范围",
         "① 学生基础维度：学院、专业、年级、班级（学号请按 R1 规则哈希后提供）\n"
         "② 借阅记录：读者哈希、ISBN、借出/应还/归还日期、续借次数、状态（近 2 个学年）\n"
         "③ 书目元数据：ISBN、书名、作者、出版社、出版年、中图法分类号、索书号、页数、定价、馆藏地、复本数"),
        ("四、脱敏要求", "见「④ 脱敏规则」页；核心是学号哈希（R1）、姓名不导出（R2）、日期截断到日（R3）"),
        ("五、数据形式", "CSV 或 Excel 单次快照即可（只读，不需接口对接），字段以「② 字段清单」为准"),
        ("六、保管与销毁", "数据仅存放于项目组加密移动介质与受限目录，项目结题后 30 日内删除；"
                         "成员签署保密承诺，不复制、不外传"),
        ("七、成果形式", "对外展示只呈现聚合结论（如「计算机学院借阅偏好 TOP10 分类」），不出现任何可识别个人的信息"),
        ("八、合规依据", "《中华人民共和国个人信息保护法》《数据安全法》及学校数据管理规定，遵循最小必要原则"),
        ("九、联系方式", "项目组联络人：万贝　｜　指导教师：＿＿＿＿　｜　申请日期：" + datetime.now().strftime("%Y 年 %m 月 %d 日")),
    ]
    row = 3
    for title, content in intro:
        ws.cell(row=row, column=1, value=title).font = Font(bold=True, size=11)
        ws.cell(row=row, column=1).alignment = Alignment(vertical="top")
        cell = ws.cell(row=row, column=2, value=content)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=4)
        ws.row_dimensions[row].height = max(22, 16 * (content.count("\n") + 1 + len(content) // 60))
        row += 1
    autosize(ws, {"A": 16, "B": 44, "C": 18, "D": 18})

    # ---------------- Sheet 2 字段清单（只列需要申请的字段） ----------------
    ws = wb.create_sheet("② 字段清单")
    headers = ["序号", "数据表", "表说明", "字段名", "中文名", "类型", "必填",
               "是否申请", "脱敏方式", "用途（对应 AI 场景）", "示例值"]
    ws.append(headers)
    style_header(ws)
    wanted = [item for item in rows if item["apply"] in ("是", "可选")]
    for seq, item in enumerate(wanted, start=1):
        ws.append([seq, item["table"], item["table_desc"], item["column"], item["cn"],
                   item["type"], item["required"], item["apply"], item["mask"], item["usage"], item["example"]])
        r = ws.max_row
        ws.cell(row=r, column=8).fill = APPLY_FILL.get(item["apply"], APPLY_FILL["否"])
        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=col)
            cell.border = BORDER
            cell.alignment = Alignment(vertical="top", wrap_text=(col in (3, 9, 10)))
    autosize(ws, {"A": 6, "B": 20, "C": 30, "D": 22, "E": 16, "F": 10,
                  "G": 7, "H": 10, "I": 24, "J": 34, "K": 24})
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{ws.max_row}"
    note_row = ws.max_row + 2
    ws.cell(row=note_row, column=1,
            value=f"说明：本页只列需要学校提供的字段（共 {len(wanted)} 个）；"
                  "完整数据字典（含系统自建字段）见仓库 docs/数据字典.md。").font = Font(italic=True, color="808080")

    # ---------------- Sheet 3 脱敏规则 ----------------
    ws = wb.create_sheet("③ 脱敏规则")
    ws.append(["规则", "适用对象", "处理方式", "处理前", "处理后", "说明"])
    style_header(ws)
    for rule in MASK_RULES:
        ws.append(list(rule))
    for r in range(2, ws.max_row + 1):
        for col in range(1, 7):
            ws.cell(row=r, column=col).border = BORDER
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")
    autosize(ws, {"A": 7, "B": 30, "C": 46, "D": 24, "E": 24, "F": 40})

    # ---------------- Sheet 4 不申请的字段 ----------------
    ws = wb.create_sheet("④ 不申请的字段")
    ws.append(["字段", "不申请的原因"])
    style_header(ws)
    for item in NOT_REQUESTED:
        ws.append(list(item))
    for r in range(2, ws.max_row + 1):
        for col in (1, 2):
            ws.cell(row=r, column=col).border = BORDER
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")
    autosize(ws, {"A": 34, "B": 70})

    # ---------------- Sheet 5 数据量估算 ----------------
    ws = wb.create_sheet("⑤ 数据量估算")
    ws.append(["数据", "预估规模", "备注"])
    style_header(ws)
    for item in ESTIMATE:
        ws.append(list(item))
    for r in range(2, ws.max_row + 1):
        for col in (1, 2, 3):
            ws.cell(row=r, column=col).border = BORDER
            ws.cell(row=r, column=col).alignment = Alignment(wrap_text=True, vertical="top")
    autosize(ws, {"A": 34, "B": 26, "C": 50})

    return wb


def build_markdown(rows: list[dict]) -> str:
    lines = [
        "# 智阅校园 · 数据字典",
        "",
        f"> 由 `backend/scripts/export_data_dictionary.py` 自动生成于 {datetime.now():%Y-%m-%d %H:%M}，"
        "字段以 `backend/app/db/models.py` 为准，请勿手工改本文件。",
        "",
        "「是否申请」表示该字段是否需要向学校申请脱敏数据：**是** = 需要，**可选** = 有更好，**否** = 系统自建或不涉及学校数据。",
        "",
    ]
    current = None
    for item in rows:
        if item["table"] != current:
            current = item["table"]
            lines += [
                "",
                f"## {item['table_cn']}（`{item['table']}`）",
                "",
                f"{item['table_desc']}",
                "",
                "| 字段 | 中文名 | 类型 | 必填 | 是否申请 | 脱敏方式 | 用途 | 示例 |",
                "|---|---|---|---|---|---|---|---|",
            ]
        lines.append(
            f"| `{item['column']}` | {item['cn']} | {item['type']} | {item['required']} | "
            f"{item['apply']} | {item['mask']} | {item['usage']} | {item['example'] or '—'} |"
        )
    lines += ["", "## 脱敏规则", "", "| 规则 | 对象 | 处理方式 | 处理前 | 处理后 | 说明 |", "|---|---|---|---|---|---|"]
    for rule in MASK_RULES:
        lines.append("| " + " | ".join(rule) + " |")
    lines += ["", "## 不申请的字段", "", "| 字段 | 原因 |", "|---|---|"]
    for item in NOT_REQUESTED:
        lines.append(f"| {item[0]} | {item[1]} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    rows = collect_rows()
    DOCS_DIR.mkdir(exist_ok=True)

    xlsx_path = DOCS_DIR / "数据字段清单-脱敏数据申请.xlsx"
    build_workbook(rows).save(xlsx_path)

    md_path = DOCS_DIR / "数据字典.md"
    md_path.write_text(build_markdown(rows), encoding="utf-8")

    tables = len({item["table"] for item in rows})
    apply_yes = sum(1 for item in rows if item["apply"] == "是")
    apply_opt = sum(1 for item in rows if item["apply"] == "可选")
    print(f"[dict] 表 {tables} 张、字段 {len(rows)} 个（申请 {apply_yes} 个 / 可选 {apply_opt} 个）")
    print(f"[dict] 已生成 {xlsx_path}")
    print(f"[dict] 已生成 {md_path}")


if __name__ == "__main__":
    main()
