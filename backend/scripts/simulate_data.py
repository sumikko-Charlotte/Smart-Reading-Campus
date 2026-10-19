"""生成 AI 模拟数据：在学校脱敏数据到位之前，先把智能体跑起来。

为什么要模拟而不是"随便造点数据"：
推荐和触达这两个场景，效果完全取决于数据里有没有**可学的模式**。随机数据生成出来，
推荐结果就是乱的，演示时说不清「凭什么推这本」。所以这里的生成规则是刻意设计的：

    学院 → 主兴趣分类（计算机学院偏 TP，人文学院偏 I/K/B）
    借阅 → 主分类 60% / 次分类 25% / 跨类 15%
    时间 → 学期内密集、寒暑假稀疏
    收藏 → 从借过的书里挑，评分集中在 4-5

这样跑出来的推荐理由才站得住：「你借过 3 本 TP 类，这本同分类且可借」。

所有模拟数据都带 data_source='simulated'。真实数据到位后执行 `--purge` 精确清除，
不会误伤已有的真实数据或人工录入的数据。

用法：
    python scripts/simulate_data.py                 # 默认 200 学生 / 3000 借阅
    python scripts/simulate_data.py --students 500 --borrows 8000
    python scripts/simulate_data.py --purge         # 只清除模拟数据（保留书目）
    python scripts/simulate_data.py --purge --purge-books   # 连模拟书目一起清
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, func, select  # noqa: E402

from app.core.enums import BookSource, BorrowSource, BorrowStatus, ReadingEventType, UserRole  # noqa: E402
from app.core.security import new_id  # noqa: E402
from app.db.base import SessionLocal, init_db  # noqa: E402
from app.db.models import Book, BookFavorite, BorrowRecord, ReadingEvent, User  # noqa: E402

SIM = "simulated"

# ------------------------------------------------------------------ 书目池
# 真实存在的书，用于在馆藏数据到位前撑起一个有区分度的书目空间。
# 字段：isbn, 书名, 作者, 出版社, 出版年, 中图法分类号, 标签, 页数, 定价
BOOK_POOL: list[tuple] = [
    # ---- TP 计算机 ----
    ("9787115428028", "深度学习", "Ian Goodfellow", "人民邮电出版社", "2017", "TP181", ["人工智能", "机器学习"], 652, 168.0),
    ("9787115546081", "Python编程：从入门到实践", "Eric Matthes", "人民邮电出版社", "2020", "TP311", ["Python", "入门"], 459, 89.0),
    ("9787111187776", "算法导论", "Thomas H. Cormen", "机械工业出版社", "2013", "TP301", ["算法", "计算机"], 780, 128.0),
    ("9787121155352", "代码大全", "Steve McConnell", "电子工业出版社", "2012", "TP311", ["软件工程", "编程"], 914, 128.0),
    ("9787111544937", "计算机网络：自顶向下方法", "James Kurose", "机械工业出版社", "2018", "TP393", ["网络", "教材"], 612, 89.0),
    ("9787111636663", "Vue.js 设计与实现", "霍春阳", "机械工业出版社", "2022", "TP393", ["前端", "Vue"], 420, 99.0),
    ("9787121362217", "推荐系统实践", "项亮", "电子工业出版社", "2012", "TP391", ["推荐系统", "算法"], 200, 49.0),
    ("9787111676515", "机器学习公式详解", "谢文睿", "机械工业出版社", "2021", "TP181", ["机器学习", "数学"], 312, 89.0),
    ("9787302511663", "统计学习方法", "李航", "清华大学出版社", "2019", "TP181", ["机器学习", "统计"], 464, 79.0),
    ("9787111213826", "重构：改善既有代码的设计", "Martin Fowler", "机械工业出版社", "2019", "TP311", ["软件工程", "编程"], 448, 99.0),
    ("9787111158370", "数据库系统概念", "Abraham Silberschatz", "机械工业出版社", "2021", "TP311", ["数据库", "教材"], 780, 128.0),
    ("9787111641247", "深入理解计算机系统", "Randal E. Bryant", "机械工业出版社", "2016", "TP303", ["计算机", "底层"], 737, 139.0),
    ("9787115523303", "操作系统导论", "Remzi Arpaci-Dusseau", "人民邮电出版社", "2019", "TP316", ["操作系统", "教材"], 520, 108.0),
    ("9787111407010", "人月神话", "Frederick P. Brooks", "清华大学出版社", "2015", "TP311", ["软件工程", "经典"], 320, 59.0),
    # ---- I 文学 ----
    ("9787020002207", "红楼梦", "曹雪芹", "人民文学出版社", "1996", "I242", ["古典文学", "名著"], 1606, 59.7),
    ("9787544253994", "百年孤独", "加西亚·马尔克斯", "南海出版公司", "2011", "I775", ["拉美文学", "魔幻现实主义"], 360, 39.5),
    ("9787506365437", "活着", "余华", "作家出版社", "2012", "I247", ["当代文学", "小说"], 191, 28.0),
    ("9787020024759", "围城", "钱锺书", "人民文学出版社", "1991", "I246", ["现代文学", "小说"], 359, 36.0),
    ("9787530212004", "平凡的世界", "路遥", "北京十月文艺出版社", "2017", "I247", ["当代文学", "现实主义"], 1631, 108.0),
    ("9787020083190", "我与地坛", "史铁生", "人民文学出版社", "2011", "I267", ["散文", "生命"], 234, 32.0),
    ("9787532757329", "月亮与六便士", "毛姆", "上海译文出版社", "2012", "I561", ["外国文学", "小说"], 288, 32.0),
    ("9787544270878", "解忧杂货店", "东野圭吾", "南海出版公司", "2014", "I313", ["日本文学", "小说"], 291, 39.5),
    ("9787540476922", "房思琪的初恋乐园", "林奕含", "湖南文艺出版社", "2018", "I247", ["当代文学", "社会议题"], 288, 45.0),
    # ---- K 历史 ----
    ("9787508647357", "人类简史", "尤瓦尔·赫拉利", "中信出版社", "2014", "K02", ["历史", "文明"], 440, 68.0),
    ("9787108009821", "万历十五年", "黄仁宇", "生活·读书·新知三联书店", "1997", "K248", ["明史", "历史"], 288, 28.0),
    ("9787532757879", "枪炮、病菌与钢铁", "贾雷德·戴蒙德", "上海译文出版社", "2016", "K02", ["文明史", "人类学"], 493, 68.0),
    ("9787108009822", "中国历代政治得失", "钱穆", "生活·读书·新知三联书店", "2012", "K207", ["政治史", "中国历史"], 178, 26.0),
    ("9787549533671", "丝绸之路：一部全新的世界史", "彼得·弗兰科潘", "浙江大学出版社", "2016", "K1", ["世界史", "文明"], 656, 128.0),
    # ---- B 哲学 / 心理 ----
    ("9787508633558", "思考，快与慢", "丹尼尔·卡尼曼", "中信出版社", "2012", "B80", ["心理学", "决策"], 418, 69.0),
    ("9787111495482", "被讨厌的勇气", "岸见一郎", "机械工业出版社", "2015", "B84", ["心理学", "自我成长"], 219, 39.8),
    ("9787544271790", "苏菲的世界", "乔斯坦·贾德", "作家出版社", "2007", "B1", ["哲学", "入门"], 535, 45.0),
    ("9787108041586", "乡土中国", "费孝通", "生活·读书·新知三联书店", "2013", "C912", ["社会学", "中国社会"], 152, 28.0),
    ("9787115136251", "心理学与生活", "理查德·格里格", "人民邮电出版社", "2016", "B84", ["心理学", "教材"], 618, 98.0),
    ("9787508647548", "非暴力沟通", "马歇尔·卢森堡", "华夏出版社", "2018", "C912", ["沟通", "心理学"], 232, 45.0),
    # ---- F 经济 / 管理 ----
    ("9787301256909", "经济学原理", "N.格里高利·曼昆", "北京大学出版社", "2015", "F0", ["经济学", "教材"], 528, 88.0),
    ("9787508649610", "穷查理宝典", "彼得·考夫曼", "中信出版社", "2016", "F83", ["投资", "思维"], 560, 88.0),
    ("9787544270205", "国富论", "亚当·斯密", "商务印书馆", "2015", "F09", ["经济学", "经典"], 480, 68.0),
    ("9787508684055", "原则", "瑞·达利欧", "中信出版社", "2018", "F27", ["管理", "思维"], 576, 98.0),
    ("9787508649719", "从0到1", "彼得·蒂尔", "中信出版社", "2015", "F27", ["创业", "商业"], 224, 45.0),
    ("9787521701460", "置身事内：中国政府与经济发展", "兰小欢", "上海人民出版社", "2021", "F12", ["中国经济", "政策"], 340, 65.0),
    # ---- O / Q 理科 ----
    ("9787040396638", "高等数学（上册）", "同济大学数学系", "高等教育出版社", "2014", "O13", ["数学", "教材"], 424, 45.0),
    ("9787040396645", "线性代数", "同济大学数学系", "高等教育出版社", "2014", "O151", ["数学", "教材"], 280, 36.0),
    ("9787040459999", "概率论与数理统计", "盛骤", "高等教育出版社", "2019", "O21", ["数学", "统计"], 400, 49.0),
    ("9787030218384", "数学之美", "吴军", "人民邮电出版社", "2020", "O1", ["数学", "科普"], 312, 69.0),
    ("9787108015174", "自私的基因", "理查德·道金斯", "中信出版社", "2012", "Q11", ["生物", "进化"], 400, 58.0),
    # ---- H / J / G ----
    ("9787513814041", "新概念英语（第二册）", "L.G.亚历山大", "外语教学与研究出版社", "2019", "H319", ["英语", "教材"], 380, 39.0),
    ("9787513814058", "英语写作手册", "威廉·斯特伦克", "外语教学与研究出版社", "2018", "H315", ["英语", "写作"], 200, 36.0),
    ("9787102063959", "艺术的故事", "贡布里希", "广西美术出版社", "2015", "J110", ["艺术史", "美术"], 688, 280.0),
    ("9787115405937", "摄影构图学", "李少白", "人民邮电出版社", "2017", "J406", ["摄影", "构图"], 240, 79.0),
    ("9787544256049", "如何阅读一本书", "莫提默·艾德勒", "商务印书馆", "2016", "G792", ["阅读方法", "学习"], 424, 46.0),
    ("9787512415037", "学习之道", "芭芭拉·奥克利", "机械工业出版社", "2016", "G442", ["学习方法", "认知"], 280, 49.0),
    ("9787549620346", "认知觉醒", "周岭", "人民邮电出版社", "2020", "G44", ["自我成长", "认知"], 320, 59.8),
    # ---- 补充：扩宽候选空间，避免「借过的书排除后无书可推」 ----
    ("9787115547545", "流畅的Python", "Luciano Ramalho", "人民邮电出版社", "2022", "TP311", ["Python", "进阶"], 792, 139.0),
    ("9787111213827", "设计模式：可复用面向对象软件的基础", "Erich Gamma", "机械工业出版社", "2019", "TP311", ["设计模式", "软件工程"], 395, 79.0),
    ("9787115275790", "JavaScript高级程序设计", "Nicholas C. Zakas", "人民邮电出版社", "2020", "TP312", ["前端", "JavaScript"], 896, 129.0),
    ("9787115367099", "图解HTTP", "上野宣", "人民邮电出版社", "2014", "TP393", ["网络", "入门"], 352, 49.0),
    ("9787115479730", "Redis设计与实现", "黄健宏", "机械工业出版社", "2018", "TP311", ["数据库", "缓存"], 388, 79.0),
    ("9787115351593", "MySQL必知必会", "Ben Forta", "人民邮电出版社", "2019", "TP311", ["数据库", "入门"], 240, 39.0),
    ("9787121318924", "大话数据结构", "程杰", "清华大学出版社", "2017", "TP311", ["数据结构", "算法"], 440, 59.0),
    ("9787115428029", "程序员修炼之道", "Andrew Hunt", "电子工业出版社", "2020", "TP311", ["软件工程", "职业成长"], 352, 89.0),
    ("9787115473899", "Python数据分析", "Wes McKinney", "机械工业出版社", "2019", "TP311", ["数据分析", "Python"], 480, 99.0),
    ("9787121295751", "软件随想录", "Joel Spolsky", "人民邮电出版社", "2016", "TP311", ["软件工程", "随笔"], 320, 59.0),
    ("9787536692930", "三体", "刘慈欣", "重庆出版社", "2008", "I247", ["科幻", "中国文学"], 302, 23.0),
    ("9787536693968", "球状闪电", "刘慈欣", "四川科学技术出版社", "2016", "I247", ["科幻", "中国文学"], 320, 32.0),
    ("9787544258609", "白夜行", "东野圭吾", "南海出版公司", "2017", "I313", ["日本文学", "推理"], 467, 39.5),
    ("9787544258616", "嫌疑人X的献身", "东野圭吾", "南海出版公司", "2014", "I313", ["日本文学", "推理"], 320, 35.0),
    ("9787020042494", "小王子", "圣埃克苏佩里", "人民文学出版社", "2003", "I565", ["外国文学", "童话"], 99, 22.0),
    ("9787532758296", "局外人", "阿尔贝·加缪", "上海译文出版社", "2013", "I565", ["外国文学", "存在主义"], 128, 28.0),
    ("9787532758302", "人间失格", "太宰治", "上海译文出版社", "2016", "I313", ["日本文学", "小说"], 224, 32.0),
    ("9787530216804", "边城", "沈从文", "北京十月文艺出版社", "2017", "I246", ["现代文学", "小说"], 208, 29.0),
    ("9787506365444", "许三观卖血记", "余华", "作家出版社", "2012", "I247", ["当代文学", "小说"], 259, 32.0),
    ("9787108009432", "我们仨", "杨绛", "生活·读书·新知三联书店", "2003", "I267", ["散文", "回忆录"], 165, 28.0),
    ("9787544270014", "撒哈拉的故事", "三毛", "北京十月文艺出版社", "2011", "I267", ["散文", "旅行"], 254, 32.0),
    ("9787801656087", "明朝那些事儿（第一部）", "当年明月", "中国海关出版社", "2009", "K248", ["明史", "通俗历史"], 288, 29.8),
    ("9787101003048", "史记", "司马迁", "中华书局", "2014", "K204", ["史学", "经典"], 1200, 128.0),
    ("9787508660126", "全球通史", "斯塔夫里阿诺斯", "北京大学出版社", "2016", "K10", ["世界史", "教材"], 1100, 128.0),
    ("9787108009823", "叫魂：1768年中国妖术大恐慌", "孔飞力", "生活·读书·新知三联书店", "2014", "K249", ["清史", "社会史"], 356, 45.0),
    ("9787508672113", "天朝的崩溃", "茅海建", "生活·读书·新知三联书店", "2017", "K253", ["近代史", "历史"], 528, 68.0),
    ("9787208061408", "乌合之众：大众心理研究", "古斯塔夫·勒庞", "中央编译出版社", "2014", "B84", ["社会心理", "经典"], 232, 39.8),
    ("9787518404070", "自卑与超越", "阿尔弗雷德·阿德勒", "中国轻工业出版社", "2016", "B84", ["心理学", "自我成长"], 280, 45.0),
    ("9787559617021", "心流：最优体验心理学", "米哈里·契克森米哈赖", "中信出版社", "2017", "B84", ["心理学", "专注"], 400, 69.0),
    ("9787108009778", "中国哲学简史", "冯友兰", "北京大学出版社", "2013", "B2", ["哲学", "中国思想"], 380, 58.0),
    ("9787521702542", "薛兆丰经济学讲义", "薛兆丰", "中信出版社", "2018", "F0", ["经济学", "通识"], 448, 68.0),
    ("9787508688893", "贫穷的本质", "阿比吉特·班纳吉", "中信出版社", "2018", "F11", ["发展经济", "社会"], 340, 58.0),
    ("9787559600665", "影响力", "罗伯特·西奥迪尼", "北京联合出版公司", "2018", "F71", ["心理", "营销"], 400, 68.0),
    ("9787511346873", "金字塔原理", "芭芭拉·明托", "南海出版公司", "2013", "F27", ["思维", "表达"], 320, 68.0),
    ("9787508674797", "高效能人士的七个习惯", "史蒂芬·柯维", "中国青年出版社", "2018", "F27", ["自我管理", "效率"], 380, 59.0),
    ("9787121352794", "第五项修炼", "彼得·圣吉", "中信出版社", "2018", "F27", ["管理", "组织"], 460, 78.0),
    ("9787535732309", "时间简史", "史蒂芬·霍金", "湖南科学技术出版社", "2018", "O4", ["物理", "科普"], 240, 45.0),
    ("9787030241450", "基因传", "悉达多·穆克吉", "中信出版社", "2018", "Q3", ["生物", "科普"], 600, 88.0),
    ("9787102078748", "美的历程", "李泽厚", "生活·读书·新知三联书店", "2017", "J01", ["美学", "艺术"], 320, 58.0),
    ("9787519275397", "刻意练习", "安德斯·艾利克森", "机械工业出版社", "2016", "G442", ["学习方法", "成长"], 300, 49.0),
    # ---- 补充：理科与长尾，避免某些学院「借过的书排除后无书可推」 ----
    ("9787040287165", "数学分析（上册）", "华东师范大学数学系", "高等教育出版社", "2010", "O17", ["数学", "分析"], 420, 42.0),
    ("9787040288537", "高等代数", "北京大学数学系", "高等教育出版社", "2013", "O15", ["数学", "代数"], 400, 39.0),
    ("9787040273151", "常微分方程", "王高雄", "高等教育出版社", "2006", "O175", ["数学", "方程"], 320, 32.0),
    ("9787040288230", "复变函数", "钟玉泉", "高等教育出版社", "2013", "O174", ["数学", "复分析"], 300, 30.0),
    ("9787111557265", "离散数学及其应用", "Kenneth H. Rosen", "机械工业出版社", "2019", "O158", ["离散数学", "计算机"], 820, 128.0),
    ("9787030233588", "从一到无穷大", "乔治·伽莫夫", "科学出版社", "2019", "O1", ["数学", "科普"], 320, 58.0),
    ("9787535732637", "上帝掷骰子吗：量子物理史话", "曹天元", "北京联合出版公司", "2019", "O413", ["物理", "科普"], 400, 59.0),
    ("9787040446937", "大学物理学（上册）", "张三慧", "清华大学出版社", "2018", "O4", ["物理", "教材"], 380, 45.0),
    ("9787108012340", "生命是什么", "埃尔温·薛定谔", "商务印书馆", "2018", "Q1", ["生物", "科普"], 180, 32.0),
    ("9787100030129", "物种起源", "查尔斯·达尔文", "商务印书馆", "2017", "Q11", ["生物", "进化"], 480, 58.0),
    ("9787532739752", "追风筝的人", "卡勒德·胡赛尼", "上海人民出版社", "2006", "I372", ["外国文学", "小说"], 362, 36.0),
    ("9787544256032", "挪威的森林", "村上春树", "上海译文出版社", "2018", "I313", ["日本文学", "小说"], 384, 45.0),
    ("9787544293395", "霍乱时期的爱情", "加西亚·马尔克斯", "南海出版公司", "2020", "I775", ["拉美文学", "小说"], 401, 58.0),
    ("9787542668463", "大问题：简明哲学导论", "罗伯特·所罗门", "清华大学出版社", "2018", "B0", ["哲学", "入门"], 480, 78.0),
    ("9787100023480", "西方哲学史", "罗素", "商务印书馆", "2015", "B5", ["哲学史", "经典"], 900, 98.0),
]

# 学院 → 专业与主兴趣分类
COLLEGE_PROFILE: dict[str, tuple[list[str], list[str]]] = {
    "计算机学院": (["计算机科学与技术", "软件工程", "数据科学与大数据技术"], ["TP", "O"]),
    "信息与通信工程学院": (["通信工程", "信息工程", "电子信息科学与技术"], ["TP", "O"]),
    "人工智能学院": (["人工智能", "智能科学与技术", "自动化"], ["TP", "O"]),
    "网络空间安全学院": (["网络空间安全", "信息安全"], ["TP"]),
    "经济管理学院": (["工商管理", "信息管理与信息系统", "电子商务"], ["F", "C"]),
    "人文学院": (["汉语言文学", "英语", "法学"], ["I", "K", "B"]),
    "数字媒体与设计艺术学院": (["数字媒体艺术", "视觉传达设计", "工业设计"], ["J", "I"]),
    "理学院": (["数学与应用数学", "应用物理学"], ["O", "Q"]),
    "国际学院": (["电信工程及管理", "物联网工程"], ["F", "H", "TP"]),
    "马克思主义学院": (["思想政治教育"], ["C", "B"]),
}

EVENT_WEIGHTS = [
    (ReadingEventType.SEARCH, 0.40),
    (ReadingEventType.VIEW_BOOK, 0.35),
    (ReadingEventType.AI_CHAT, 0.15),
    (ReadingEventType.SIGNUP, 0.05),
    (ReadingEventType.NOTIFICATION_READ, 0.05),
]


def _ensure_books(db, target: int) -> tuple[int, int]:
    """补齐书目到 target 本。返回 (新增, 现有)。"""
    existing = db.scalar(select(func.count()).select_from(Book).where(Book.is_deleted.is_(False))) or 0
    created = 0
    if existing >= target:
        return 0, existing

    isbns = set(db.scalars(select(Book.isbn)).all())
    rng = random.Random(20261019)
    for isbn, title, author, publisher, year, clc, tags, pages, price in BOOK_POOL:
        if existing + created >= target:
            break
        if isbn in isbns:
            continue
        copies = rng.choice([2, 3, 3, 4, 5, 6])
        available = max(0, copies - rng.randint(0, 2))
        db.add(
            Book(
                book_id=new_id("book"),
                isbn=isbn,
                title=title,
                author=author,
                publisher=publisher,
                publish_date=year,
                category=clc,
                clc_code=clc,
                call_no=f"{clc}/{author[:2]}",
                pages=pages,
                price=price,
                binding="平装",
                lib_location=rng.choice(["沙河三层 A 区", "沙河二层 C 区", "沙河四层 B 区", "本部二层"]),
                summary=f"《{title}》由{author}著，{publisher}{year}年出版，是{('、'.join(tags))}方向较有代表性的一本书。",
                tags=tags,
                source=BookSource.LIBRARY.value,
                total_copies=copies,
                available_copies=available,
                borrow_count=rng.randint(5, 120),
                data_source=SIM,
            )
        )
        isbns.add(isbn)
        created += 1
    db.flush()
    return created, existing + created


def _build_students(db, count: int, rng: random.Random) -> list[User]:
    colleges = list(COLLEGE_PROFILE)
    rows: list[User] = []
    for index in range(count):
        college = rng.choice(colleges)
        majors, _ = COLLEGE_PROFILE[college]
        grade = rng.choice(["2022", "2023", "2024", "2025", "2026"])
        student_no = f"SIM{20260000 + index:08d}"
        if db.scalar(select(User).where(User.student_no == student_no)) is not None:
            continue
        user = User(
            user_id=new_id("user"),
            student_no=student_no,
            name=f"模拟{index:03d}",
            role=UserRole.STUDENT.value,
            college=college,
            major=rng.choice(majors),
            class_no=f"{grade}{200 + index % 20}",
            grade=grade,
            data_source=SIM,
        )
        db.add(user)
        rows.append(user)
    db.flush()
    return rows


def _pick_books_by_clc(all_books: list[Book], clc_prefixes: list[str]) -> list[Book]:
    return [book for book in all_books if any((book.clc_code or "").startswith(prefix) for prefix in clc_prefixes)]


def _semester_weight(moment: datetime) -> float:
    """学期内权重高、寒暑假低，让借阅时间分布接近真实。"""
    month = moment.month
    return 1.0 if month in (3, 4, 5, 6, 9, 10, 11, 12) else 0.35


def _generate(db, students: list[User], borrow_target: int, days: int, rng: random.Random) -> dict[str, int]:
    all_books = db.scalars(select(Book).where(Book.is_deleted.is_(False))).all()
    if not all_books:
        raise SystemExit("书目为空，请先把 --books 设为大于 0 以补充样本书目")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    borrows = favorites = events = 0
    per_student = max(1, borrow_target // max(1, len(students)))

    for student in students:
        _, interest_clc = COLLEGE_PROFILE.get(student.college, ([], ["I"]))
        primary = _pick_books_by_clc(all_books, interest_clc[:1]) or all_books
        secondary = _pick_books_by_clc(all_books, interest_clc[1:2])

        history: list[Book] = []
        for _ in range(rng.randint(max(1, per_student - 4), per_student + 4)):
            roll = rng.random()
            if roll < 0.60 or not secondary:
                pool = primary
            elif roll < 0.85:
                pool = secondary
            else:
                pool = all_books
            book = rng.choice(pool)

            # 日期：按学期权重拒绝采样，最多试 6 次
            offset_days = rng.randint(1, days)
            for _ in range(6):
                if rng.random() < _semester_weight(now - timedelta(days=offset_days)):
                    break
                offset_days = rng.randint(1, days)

            borrowed_at = now - timedelta(days=offset_days, hours=rng.randint(0, 23))
            due_at = borrowed_at + timedelta(days=30)
            returned = rng.random() < 0.82
            returned_at = borrowed_at + timedelta(days=rng.randint(3, 44)) if returned else None
            if returned_at is not None and returned_at > now:
                returned_at = now - timedelta(days=rng.randint(0, 5))
            if returned_at is not None:
                status = BorrowStatus.RETURNED.value
            elif due_at < now:
                status = BorrowStatus.OVERDUE.value
            else:
                status = BorrowStatus.BORROWING.value

            db.add(
                BorrowRecord(
                    borrow_id=new_id("borrow"),
                    user_id=student.user_id,
                    book_id=book.book_id,
                    isbn=book.isbn,
                    lib_barcode=f"SIM-{rng.randint(100000, 999999)}",
                    borrowed_at=borrowed_at,
                    due_at=due_at,
                    returned_at=returned_at,
                    renew_count=rng.choice([0, 0, 0, 1, 1, 2]),
                    status=status,
                    source=BorrowSource.LIBRARY.value,
                    data_source=SIM,
                )
            )
            borrows += 1
            history.append(book)

        # 收藏：从借过的书里挑，评分偏高（人只会收藏喜欢的）
        # 先按 book_id 去重：同一个人可能重复借同一本书，收藏表却有 (user, book) 唯一约束
        unique_history = list({book.book_id: book for book in history}.values())
        if unique_history and rng.random() < 0.45:
            for book in rng.sample(unique_history, min(len(unique_history), rng.randint(1, 3))):
                db.add(
                    BookFavorite(
                        favorite_id=new_id("favorite"),
                        user_id=student.user_id,
                        book_id=book.book_id,
                        rating=rng.choice([3, 4, 4, 5, 5]),
                        note="",
                        data_source=SIM,
                    )
                )
                favorites += 1

        # 行为埋点
        kinds = [item[0] for item in EVENT_WEIGHTS]
        weights = [item[1] for item in EVENT_WEIGHTS]
        for _ in range(rng.randint(2, 8)):
            kind = rng.choices(kinds, weights=weights, k=1)[0]
            book = rng.choice(history) if history and kind != ReadingEventType.SEARCH else None
            db.add(
                ReadingEvent(
                    event_id=new_id("event"),
                    user_id=student.user_id,
                    event_type=kind.value,
                    book_id=book.book_id if book is not None else "",
                    keyword=rng.choice(["机器学习", "心理学", "余华", "考研数学", "时间管理"]) if kind == ReadingEventType.SEARCH else "",
                    duration_sec=rng.randint(20, 600),
                    scene="pc",
                    created_at=now - timedelta(days=rng.randint(0, days)),
                    data_source=SIM,
                )
            )
            events += 1

    db.flush()
    return {"borrows": borrows, "favorites": favorites, "events": events}


def purge(db, purge_books: bool = False) -> dict[str, int]:
    counts = {}
    for model, label in ((BorrowRecord, "borrows"), (BookFavorite, "favorites"), (ReadingEvent, "events")):
        result = db.execute(delete(model).where(model.data_source == SIM))
        counts[label] = result.rowcount or 0
    result = db.execute(delete(User).where(User.data_source == SIM))
    counts["users"] = result.rowcount or 0
    if purge_books:
        result = db.execute(delete(Book).where(Book.data_source == SIM))
        counts["books"] = result.rowcount or 0
    else:
        counts["books"] = 0
    db.commit()
    return counts


def stats(db) -> dict[str, int]:
    def count(model):
        return db.scalar(select(func.count()).select_from(model).where(model.data_source == SIM)) or 0

    return {
        "users": count(User),
        "books": count(Book),
        "borrows": count(BorrowRecord),
        "favorites": count(BookFavorite),
        "events": count(ReadingEvent),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="生成 / 清除 AI 模拟数据")
    parser.add_argument("--students", type=int, default=200, help="模拟学生数，默认 200")
    parser.add_argument("--borrows", type=int, default=1600, help="借阅记录总数，默认 1600（人均约 8 本）")
    parser.add_argument("--books", type=int, default=105, help="书目补足到多少本，默认 105")
    parser.add_argument("--days", type=int, default=180, help="借阅时间跨度（天），默认 180")
    parser.add_argument("--seed", type=int, default=42, help="随机种子，同一种子结果可复现")
    parser.add_argument("--purge", action="store_true", help="只清除模拟数据，不生成")
    parser.add_argument("--purge-books", action="store_true", help="清除时连同模拟书目一起删")
    parser.add_argument("--keep-books", action="store_true", help="重新生成时保留已有模拟书目")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.purge:
            counts = purge(db, purge_books=args.purge_books)
            print("[purge] 已清除：", counts)
            print("[purge] 剩余模拟数据：", stats(db))
            return

        # 重新生成前先清掉旧的模拟行为数据，避免重复累加
        removed = purge(db, purge_books=False)
        print("[sim] 清理上一批模拟行为数据：", removed)

        added, total_books = _ensure_books(db, args.books)
        print(f"[sim] 书目：新增 {added} 本，当前共 {total_books} 本")

        rng = random.Random(args.seed)
        students = _build_students(db, args.students, rng)
        print(f"[sim] 学生：新增 {len(students)} 人（账号 SIM2026xxxx，密码 123456）")

        produced = _generate(db, students, args.borrows, args.days, rng)
        db.commit()
        print(f"[sim] 行为数据：借阅 {produced['borrows']}、收藏 {produced['favorites']}、埋点 {produced['events']}")
        print("[sim] 当前模拟数据总量：", stats(db))
        print("\n提示：真实数据到位后执行  python scripts/simulate_data.py --purge --purge-books  即可清除")
    finally:
        db.close()


if __name__ == "__main__":
    main()
