import streamlit as st
import streamlit.components.v1 as components
import datetime
import re
import difflib
import html
from typing import List, Dict, Any, Tuple, Optional
from templates_data import WEATHER_TEMPLATES
from corrector import correct_text
from templates import RAIN_STORM_TEMPLATES


MOCK_TOWNS = [
    {"name": "平乐镇"}, {"name": "二塘镇"}, {"name": "沙子镇"}, 
    {"name": "源头镇"}, {"name": "同安镇"}, {"name": "张家镇"}, 
    {"name": "阳安乡"}, {"name": "桥亭乡"}, {"name": "青龙乡"}, 
    {"name": "大发乡"}
]
DOUBLE_REGION_TEMPLATES = ["过程", "实况", "继续发布", "预警升级", "预警降级"]
WEATHER_LEVELS = {
    "雷电": ["黄色", "橙色", "红色"],
    "雷雨大风": ["黄色", "橙色", "红色"],
    "大风": ["蓝色", "黄色", "橙色", "红色"],
    "寒潮": ["蓝色", "黄色", "橙色"],
    "高温": ["黄色", "橙色", "红色"],
    "冰雹": ["橙色", "红色"],
    "道路结冰": ["黄色", "橙色", "红色"],
    "霜冻": ["蓝色", "黄色", "橙色"],
    "大雾": ["黄色", "橙色", "红色"],
    "干旱": ["橙色", "红色"],
    "台风": ["蓝色", "黄色", "橙色", "红色"],
    "暴雪": ["蓝色", "黄色", "橙色", "红色"],
    "霾": ["黄色", "橙色"]
}

TOWN_NAMES = sorted([data["name"] for data in MOCK_TOWNS])

IMAGE_BASE64_PLACEHOLDER = "iVBORw0KGgoAAAANSUhEUgAAAl"
IMAGE_BASE64 = IMAGE_BASE64_PLACEHOLDER 

# ==============================================================================
# Y1/Y2/X1/XX 范围校验规则配置
# ==============================================================================
# 格式说明：
# - None 表示无范围限制
# - (min, max, "closed_closed") 表示 min ≤ value ≤ max
# - (min, max, "open_closed") 表示 min < value ≤ max
# - (min, max, "closed_open") 表示 min ≤ value < max
# - (min, None, "gte") 表示 value ≥ min
# - (None, max, "lte") 表示 value ≤ max
# - (None, max, "lt") 表示 value < max
# - "special_xxx" 表示需要特殊处理（如 Y1+Y2 的组合判断）

RAINFALL_VALIDATION_RULES = {
    "提前": {
        "黄色": {"Y1": None, "Y2": (50, 120, "closed_open"), "X1": None, "XX": None},
        "橙色": {"Y1": None, "Y2": (50, 120, "closed_open"), "X1": None, "XX": None},
        "红色": {"Y1": None, "Y2": (120, None, "gte"), "X1": None, "XX": None},
    },
    "过程": {
        "黄色": {"Y1": (None, 50, "lt"), "Y2": "special_sum_lt_120", "X1": (1, 2, "open_closed"), "XX": None},
        "橙色": {"Y1": (None, 60, "lt"), "Y2": "special_sum_gte_120", "X1": (1, 2, "open_closed"), "XX": None},
        "红色": {"Y1": (20, 40, "closed_open"), "Y2": (None, 120, "lt"), "X1": (1, 2, "open_closed"), "XX": None},
    },
    "实况": {
        "黄色": {"Y1": (20, 40, "closed_open"), "Y2": (None, 120, "lt"), "X1": (1, 2, "open_closed"), "XX": (3, 6, "open_closed")},
        "橙色": {"Y1": (30, 50, "closed_open"), "Y2": (None, 120, "lt"), "X1": (1, 2, "open_closed"), "XX": (3, 6, "open_closed")},
        "红色": {"Y1": (None, 60, "lt"), "Y2": None, "X1": (1, 2, "open_closed"), "XX": (None, 3, "lte")},
    },
    "实况趋减": {
        "黄色": {"Y1": (20, 40, "closed_open"), "Y2": (None, 20, "lte"), "X1": (1, 2, "open_closed"), "XX": (None, 6, "lte")},
        "橙色": {"Y1": (30, 50, "closed_open"), "Y2": (None, 20, "lte"), "X1": (1, 2, "open_closed"), "XX": (None, 3, "lte")},
        "红色": {"Y1": (None, 60, "lt"), "Y2": (None, 30, "lte"), "X1": (1, 2, "open_closed"), "XX": (None, 3, "lte")},
    },
    "继续发布": {
        "黄色": {"Y1": None, "Y2": (50, 120, "closed_open"), "X1": None, "XX": None},
        "橙色": {"Y1": None, "Y2": (50, 120, "closed_open"), "X1": None, "XX": None},
        "红色": {"Y1": None, "Y2": (120, None, "gte"), "X1": None, "XX": None},
    },
    "预警升级": {
        "黄升橙色": {"Y1": (50, None, "gte"), "Y2": (50, 120, "closed_open"), "X1": (3, 6, "open_closed"), "XX": None},
        "黄升红色": {"Y1": None, "Y2": (120, None, "gte"), "X1": (3, 6, "open_closed"), "XX": None},
        "橙升红色": {"Y1": (None, 120, "lt"), "Y2": "special_sum_gte_120", "X1": (None, 3, "lte"), "XX": None},
    },
    "预警降级": {
        "橙降黄色": {"Y1": (50, 120, "closed_open"), "Y2": (50, 120, "closed_open"), "X1": (None, 3, "lte"), "XX": None},
        "红降黄色": {"Y1": (120, None, "gte"), "Y2": (50, 120, "closed_open"), "X1": None, "XX": None},
        "红降橙色": {"Y1": (120, None, "gte"), "Y2": (50, 120, "closed_open"), "X1": None, "XX": None},
    },
}

# ==============================================================================
# 3. NAVIGATION CALLBACKS (页面跳转回调)
# ==============================================================================

def go_to_main_page():
    st.session_state.page = 'main_page'

def go_to_third_page():
    st.session_state.page = 'third_page'

def select_all_towns():
    """全选所有乡镇 - 优化版本"""
    st.session_state.selected_towns = TOWN_NAMES.copy()
    for town in TOWN_NAMES:
        checkbox_key = f"town_{town}"
        st.session_state[checkbox_key] = True

def deselect_all_towns():
    """清空所有选择 - 优化版本"""
    st.session_state.selected_towns = []
    for town in TOWN_NAMES:
        checkbox_key = f"town_{town}"
        st.session_state[checkbox_key] = False

# ==============================================================================
# 4. STATE MANAGEMENT (状态初始化与回调)
# ==============================================================================

def update_datetime_state():
    """更新格式化后的日期时间字符串到session state"""
    y = st.session_state.get('sel_year', datetime.datetime.now().year)
    m = st.session_state.get('sel_month', datetime.datetime.now().month)
    d = st.session_state.get('sel_day', datetime.datetime.now().day)
    h = st.session_state.get('sel_hour', datetime.datetime.now().hour)
    mn = st.session_state.get('sel_minute', datetime.datetime.now().minute)
    
    st.session_state.selected_date = f"{y}年{m:02d}月{d:02d}日"
    st.session_state.selected_time = f"{h:02d}时{mn:02d}分"

# ==============================================================================
# 乡镇选择回调函数
# ==============================================================================

def select_all_region_1():
    """全选区域1的回调函数"""
    st.session_state.selected_towns = TOWN_NAMES.copy()
    for town in TOWN_NAMES:
        checkbox_key = f"town_{town}"
        st.session_state[checkbox_key] = True
    st.session_state.force_rerun = True

def deselect_all_region_1():
    """清空区域1的回调函数"""
    st.session_state.selected_towns = []
    for town in TOWN_NAMES:
        checkbox_key = f"town_{town}"
        st.session_state[checkbox_key] = False
    st.session_state.force_rerun = True

def select_all_region_2():
    """全选区域2的回调函数"""
    st.session_state.selected_towns_2 = TOWN_NAMES.copy()
    for town in TOWN_NAMES:
        checkbox_key_2 = f"town_checkbox_2_{town}"
        st.session_state[checkbox_key_2] = True
    st.session_state.force_rerun = True

def deselect_all_region_2():
    """清空区域2的回调函数"""
    st.session_state.selected_towns_2 = []
    for town in TOWN_NAMES:
        checkbox_key_2 = f"town_checkbox_2_{town}"
        st.session_state[checkbox_key_2] = False
    st.session_state.force_rerun = True

def initialize_session_state(): 
    """初始化所有会话状态变量"""
    now = datetime.datetime.now()
    
    # 基础页面状态
    if 'page' not in st.session_state: 
        st.session_state.page = 'main_page'
    if 'initialized' not in st.session_state:
        st.session_state.initialized = True
    if 'force_rerun' not in st.session_state:
        st.session_state.force_rerun = False    
        st.session_state.sel_year = now.year
        st.session_state.sel_month = now.month
        st.session_state.sel_day = now.day
        st.session_state.sel_hour = now.hour
        st.session_state.sel_minute = now.minute
        update_datetime_state()
    
    # 确保时间状态始终存在
    if 'sel_year' not in st.session_state:
        st.session_state.sel_year = now.year
    if 'sel_month' not in st.session_state:
        st.session_state.sel_month = now.month
    if 'sel_day' not in st.session_state:
        st.session_state.sel_day = now.day
    if 'sel_hour' not in st.session_state:
        st.session_state.sel_hour = now.hour
    if 'sel_minute' not in st.session_state:
        st.session_state.sel_minute = now.minute
    
    if 'selected_date' not in st.session_state or 'selected_time' not in st.session_state:
        update_datetime_state()

    # 乡镇选择相关状态 - 区域1和区域2都初始化为["平乐镇"]
    if 'selected_towns' not in st.session_state:
        st.session_state.selected_towns = ["平乐镇"]

    # 区域2也初始化为["平乐镇"]，保持和区域1一致
    if 'selected_towns_2' not in st.session_state:
        st.session_state.selected_towns_2 = ["平乐镇"]
    
    if 'show_second_region' not in st.session_state:
        st.session_state.show_second_region = False

    # Page 1 - 预警生成状态
    if 'p1_weather_type' not in st.session_state:
        st.session_state.p1_weather_type = list(WEATHER_LEVELS.keys())[0]
    if 'p1_generated_content' not in st.session_state:
        st.session_state.p1_generated_content = ""
    if 'p1_weather_level' not in st.session_state:
        p1_levels = get_p1_levels()
        st.session_state.p1_weather_level = p1_levels[0] if p1_levels else ""
    if 'p1_template_type' not in st.session_state:
        p1_template_types = get_p1_template_types(st.session_state.p1_weather_type, st.session_state.p1_weather_level)
        st.session_state.p1_template_type = p1_template_types[0] if p1_template_types else ""
    
    # Page 3 - 暴雨短信状态
    if 'p3_sel_year' not in st.session_state:
        st.session_state.p3_sel_year = now.year
    if 'p3_sel_month' not in st.session_state:
        st.session_state.p3_sel_month = now.month
    if 'p3_sel_day' not in st.session_state:
        st.session_state.p3_sel_day = now.day
    if 'p3_sel_hour' not in st.session_state:
        st.session_state.p3_sel_hour = now.hour
    if 'p3_sel_minute' not in st.session_state:
        st.session_state.p3_sel_minute = now.minute
    
    if 'p3_level' not in st.session_state:
        st.session_state.p3_level = "黄色"
    if 'p3_template_type' not in st.session_state:
        st.session_state.p3_template_type = "继续发布"

    # 确保区域1每个乡镇的复选框状态存在且正确
    for town in TOWN_NAMES:
        checkbox_key = f"town_{town}"
        if checkbox_key not in st.session_state:
            st.session_state[checkbox_key] = (town in st.session_state.selected_towns)

    # 确保区域2每个乡镇的复选框状态存在且正确
    for town in TOWN_NAMES:
        checkbox_key_2 = f"town_checkbox_2_{town}"
        if checkbox_key_2 not in st.session_state:
            st.session_state[checkbox_key_2] = (town in st.session_state.selected_towns_2)

    # 第三页生成结果状态
    if 'p3_short_sms' not in st.session_state:
        st.session_state.p3_short_sms = "短短信内容将显示在这里。"
    if 'p3_long_sms' not in st.session_state:
        st.session_state.p3_long_sms = "长短信内容将显示在这里。"
    if 'p3_generation_success' not in st.session_state:
        st.session_state.p3_generation_success = False
    if 'p3_validation_warnings' not in st.session_state:
        st.session_state.p3_validation_warnings = []

    # 第三页额外数据默认值
    extra_data_defaults = {
        "过去时长": "1",
        "已出现降雨": "20",
        "未来时长": "3",
        "未来降雨": "20",
        "短短信时间": "3",
        "伴随天气": "雷电、短时大风",
        "移向": "东移",
        "强度变化趋势": "维持",
        "风险类型": "城乡积涝",
        "升级提示": True,
        "云团状态": "强降雨云团已远离",
        "影响状态": "结束",
        "实际影响区域": "我县北部的沙子镇、二塘镇等乡镇",
        "降雨范围": "120-130",
        "最大降雨区域": "二塘镇鸟梨峡水库",
        "最大降雨量": "128.5",
        "局地降雨范围": "130-140"  # 新增这行
    }
    
    for key, value in extra_data_defaults.items():
        state_key = f'p3_extra_data_{key}'
        if state_key not in st.session_state:
            st.session_state[state_key] = value

# ==============================================================================
# 5. 范围校验功能
# ==============================================================================

def get_range_description(rule: Any) -> str:
    """将范围规则转换为可读的描述文字"""
    if rule is None:
        return "无限制"
    elif isinstance(rule, str):
        if rule == "special_sum_lt_120":
            return "Y1+Y2 < 120"
        elif rule == "special_sum_gte_120":
            return "Y1+Y2 ≥ 120"
        else:
            return rule
    elif isinstance(rule, tuple):
        min_val, max_val, rule_type = rule[0], rule[1], rule[2] if len(rule) > 2 else "closed_open"
        
        if rule_type == "closed_closed":
            if min_val is not None and max_val is not None:
                return f"{min_val} ≤ 值 ≤ {max_val}"
            elif min_val is not None:
                return f"≥ {min_val}"
            elif max_val is not None:
                return f"≤ {max_val}"
        elif rule_type == "open_closed":
            if min_val is not None and max_val is not None:
                return f"{min_val} < 值 ≤ {max_val}"
            elif min_val is not None:
                return f"> {min_val}"
            elif max_val is not None:
                return f"≤ {max_val}"
        elif rule_type == "closed_open":
            if min_val is not None and max_val is not None:
                return f"{min_val} ≤ 值 < {max_val}"
            elif min_val is not None:
                return f"≥ {min_val}"
            elif max_val is not None:
                return f"< {max_val}"
        elif rule_type == "gte":
            return f"≥ {min_val}"
        elif rule_type == "lte":
            return f"≤ {max_val}"
        elif rule_type == "lt":
            return f"< {max_val}"
        elif rule_type == "gt":
            return f"> {min_val}"
            
    return "无限制"

def get_short_range_description(rule: Any) -> str:
    """获取简短的范围描述，用于输入框标签"""
    if rule is None:
        return ""
    elif isinstance(rule, str):
        if rule == "special_sum_lt_120":
            return "(Y1+Y2<120)"
        elif rule == "special_sum_gte_120":
            return "(Y1+Y2≥120)"
        else:
            return ""
    elif isinstance(rule, tuple):
        min_val, max_val, rule_type = rule[0], rule[1], rule[2] if len(rule) > 2 else "closed_open"
        
        if rule_type == "closed_closed":
            if min_val is not None and max_val is not None:
                return f"({min_val}~{max_val})"
            elif min_val is not None:
                return f"(≥{min_val})"
            elif max_val is not None:
                return f"(≤{max_val})"
        elif rule_type == "open_closed":
            if min_val is not None and max_val is not None:
                return f"({min_val}<值≤{max_val})"
            elif min_val is not None:
                return f"(>{min_val})"
            elif max_val is not None:
                return f"(≤{max_val})"
        elif rule_type == "closed_open":
            if min_val is not None and max_val is not None:
                return f"({min_val}~{max_val})"
            elif min_val is not None:
                return f"(≥{min_val})"
            elif max_val is not None:
                return f"(<{max_val})"
        elif rule_type == "gte":
            return f"(≥{min_val})"
        elif rule_type == "lte":
            return f"(≤{max_val})"
        elif rule_type == "lt":
            return f"(<{max_val})"
        elif rule_type == "gt":
            return f"(>{min_val})"
            
    return ""

def get_current_validation_rules(template_type: str, level: str) -> Dict[str, Any]:
    """获取当前预警类型和等级对应的校验规则"""
    rules = RAINFALL_VALIDATION_RULES.get(template_type, {})
    return rules.get(level, {"Y1": None, "Y2": None, "X1": None, "XX": None})

def validate_single_value(value: float, rule: Any) -> Tuple[bool, str]:
    """
    校验单个值是否符合规则
    返回: (是否通过, 错误信息)
    """
    if rule is None:
        return True, ""
    
    if isinstance(rule, str):
        # 特殊规则，需要在外部处理
        return True, ""
    
    if isinstance(rule, tuple):
        min_val, max_val = rule[0], rule[1]
        rule_type = rule[2] if len(rule) > 2 else "closed_open"
        
        if rule_type == "closed_closed":
            if min_val is not None and value < min_val:
                return False, f"值 {value} 小于最小值 {min_val}"
            if max_val is not None and value > max_val:
                return False, f"值 {value} 大于最大值 {max_val}"
        elif rule_type == "open_closed":
            if min_val is not None and value <= min_val:
                return False, f"值 {value} 应大于 {min_val}"
            if max_val is not None and value > max_val:
                return False, f"值 {value} 大于最大值 {max_val}"
        elif rule_type == "closed_open":
            if min_val is not None and value < min_val:
                return False, f"值 {value} 小于最小值 {min_val}"
            if max_val is not None and value >= max_val:
                return False, f"值 {value} 大于等于最大值 {max_val}"
        elif rule_type == "gte":
            if min_val is not None and value < min_val:
                return False, f"值 {value} 应大于等于 {min_val}"
        elif rule_type == "lte":
            if max_val is not None and value > max_val:
                return False, f"值 {value} 应小于等于 {max_val}"
        elif rule_type == "lt":
            if max_val is not None and value >= max_val:
                return False, f"值 {value} 应小于 {max_val}"
        elif rule_type == "gt":
            if min_val is not None and value <= min_val:
                return False, f"值 {value} 应大于 {min_val}"
    
    return True, ""

def validate_all_values(y1: float, y2: float, x1: float, xx: float, template_type: str, level: str) -> Tuple[bool, List[str]]:
    """
    校验所有参数是否符合当前预警类型和等级的要求
    返回: (是否全部通过, 警告信息列表)
    """
    warnings = []
    rules = get_current_validation_rules(template_type, level)
    
    # 校验 Y1
    y1_rule = rules.get("Y1")
    if y1_rule is not None and not isinstance(y1_rule, str):
        is_valid, msg = validate_single_value(y1, y1_rule)
        if not is_valid:
            expected = get_range_description(y1_rule)
            warnings.append(f"⚠️ Y1(已出现降雨) 不符合范围要求：当前值={y1}，要求：{expected}")
    
    # 校验 Y2
    y2_rule = rules.get("Y2")
    if y2_rule is not None:
        if isinstance(y2_rule, str):
            if y2_rule == "special_sum_lt_120":
                if y1 + y2 >= 120:
                    warnings.append(f"⚠️ Y1+Y2 不符合要求：当前 Y1({y1})+Y2({y2})={y1+y2}，要求 Y1+Y2 < 120")
            elif y2_rule == "special_sum_gte_120":
                if y1 + y2 < 120:
                    warnings.append(f"⚠️ Y1+Y2 不符合要求：当前 Y1({y1})+Y2({y2})={y1+y2}，要求 Y1+Y2 ≥ 120")
        else:
            is_valid, msg = validate_single_value(y2, y2_rule)
            if not is_valid:
                expected = get_range_description(y2_rule)
                warnings.append(f"⚠️ Y2(未来降雨) 不符合范围要求：当前值={y2}，要求：{expected}")
    
    # 校验 X1
    x1_rule = rules.get("X1")
    if x1_rule is not None and not isinstance(x1_rule, str):
        is_valid, msg = validate_single_value(x1, x1_rule)
        if not is_valid:
            expected = get_range_description(x1_rule)
            warnings.append(f"⚠️ X1(过去时长) 不符合范围要求：当前值={x1}，要求：{expected}")
    
    # 校验 XX
    xx_rule = rules.get("XX")
    if xx_rule is not None and not isinstance(xx_rule, str):
        is_valid, msg = validate_single_value(xx, xx_rule)
        if not is_valid:
            expected = get_range_description(xx_rule)
            warnings.append(f"⚠️ XX(未来时长) 不符合范围要求：当前值={xx}，要求：{expected}")
    
    all_passed = len(warnings) == 0
    return all_passed, warnings

# ==============================================================================
# 6. CORE LOGIC (核心功能函数)
# ==============================================================================

def get_p1_levels() -> List[str]:
    return WEATHER_LEVELS.get(st.session_state.p1_weather_type, [])

def get_p1_template_types(weather_type: str, weather_level: str) -> List[str]:
    return list(WEATHER_TEMPLATES.get(weather_type, {}).get(weather_level, {}).keys())

def show_copyable_preview(text: str, ta_height: int = 72):
    """渲染可一键复制的预警内容预览框（兼容 HTTP，无需 HTTPS）。"""
    safe = html.escape(text)
    components.html(f"""
    <div style="font-family:'Microsoft YaHei',sans-serif;">
      <textarea id="pv" readonly style="
        width:calc(100% - 20px);height:{ta_height}px;padding:8px 10px;
        font-size:14px;border:1px solid #d9d9d9;border-radius:4px;
        resize:none;background:#fafafa;color:#333;line-height:1.6;
      ">{safe}</textarea>
      <div style="text-align:right;margin-top:4px;">
        <button id="cb" onclick="(function(){{
          var ta=document.getElementById('pv');
          ta.select();ta.setSelectionRange(0,99999);
          var ok=document.execCommand('copy');
          var btn=document.getElementById('cb');
          if(ok){{btn.textContent='✓ 已复制';btn.style.background='#52c41a';}}
          else{{btn.textContent='复制失败';btn.style.background='#faad14';}}
          setTimeout(function(){{btn.textContent='点击复制';btn.style.background='#ff4b4b';}},2000);
        }})()" style="
          padding:3px 14px;background:#ff4b4b;color:#fff;
          border:none;border-radius:4px;cursor:pointer;font-size:13px;
        ">点击复制</button>
      </div>
    </div>
    """, height=ta_height + 48)

def _is_minor_edit(text: str, reference: str, max_edits: int = 5) -> bool:
    """判断 text 与 reference 差异是否在 max_edits 个字以内。"""
    a = re.sub(r'\s+', '', text)
    b = re.sub(r'\s+', '', reference)
    if abs(len(a) - len(b)) > max_edits:
        return False
    matcher = difflib.SequenceMatcher(None, a, b)
    matching = sum(n for _, _, n in matcher.get_matching_blocks())
    return (len(a) + len(b) - 2 * matching) <= max_edits

def generate_weather_content():
    try:
        if any(key not in st.session_state for key in ['sel_day', 'sel_hour', 'sel_minute']):
            st.error("时间参数未初始化，请检查日期时间选择。")
            return
        
        day = st.session_state.sel_day
        hour = st.session_state.sel_hour
        minute = st.session_state.sel_minute
        
        selected_type = st.session_state.p1_weather_type
        selected_level = st.session_state.p1_weather_level
        selected_template_type = st.session_state.p1_template_type

        template = WEATHER_TEMPLATES.get(selected_type, {}).get(selected_level, {}).get(selected_template_type)

        if template:
            final_content = template.format(day=day, hour=hour, minute=minute)
            st.session_state.p1_generated_content = final_content
            st.session_state.p1_last_clean_text = final_content
            st.success("预警内容生成成功！")
        else:
            st.session_state.p1_generated_content = (
                f"⚠️ 找不到对应的预警模板\n"
                f"灾害类型: {selected_type}\n"
                f"预警等级: {selected_level}\n"
                f"用语类型: {selected_template_type}\n"
                f"请检查模板配置。"
            )
    except Exception as e:
        st.session_state.p1_generated_content = f"❌ 生成内容失败: {str(e)}"

def generate_message(level: str, template_type: str, sms_type: str, towns: List[str], date: str, time: str, extra_data: Dict[str, Any], towns_2: List[str] = None) -> str:
    try:
        # 获取第二个区域，如果未提供则使用session_state中的值
        if towns_2 is None:
            towns_2 = st.session_state.get('selected_towns_2', [])
        
        # 如果区域2为空，使用区域1的值作为默认
        if not towns_2:
            towns_2 = towns.copy()
        
        needs_double_region = template_type in DOUBLE_REGION_TEMPLATES
        
        day_part = date.split('日')[0].split('月')[-1] + "日"
        time_display = time
        short_time_format = time_display
        
        real_template_type = template_type
        is_level_change = False
        
        if template_type == "预警升级":
            real_template_type = "升级"
            is_level_change = True
        elif template_type == "预警降级":
            real_template_type = "降级"
            is_level_change = True
        
        if is_level_change:
            templates_by_level = RAIN_STORM_TEMPLATES.get(real_template_type, {})
            template_struct = templates_by_level.get(level, {})
        else:
            level_key = level.split("升")[0] if "升" in level else level.split("降")[0] if "降" in level else level
            templates_by_level = RAIN_STORM_TEMPLATES.get(level_key, {})
            template_struct = templates_by_level.get(real_template_type, {})
        
        if not template_struct:
            return f"错误：RAIN_STORM_TEMPLATES 缺少 '{real_template_type}' 的模板定义或等级'{level}'定义。"

        if sms_type == "长短信":
            template = template_struct.get("长短信")
        elif sms_type == "短短信":
            template = template_struct.get("短短信")
        
        if not template:
            return f"错误：短信模板不存在：等级'{level}'，类型'{real_template_type}'，短信类型'{sms_type}'"

        final_message = ""
        
        if sms_type == "短短信":
            message_body = template
            
            message_body = message_body.replace("X县", "平乐县")
            message_body = message_body.replace("X日", day_part)
            message_body = message_body.replace("X时X分", short_time_format)
            
            # 区域替换逻辑 - 支持双区域
            message_body = message_body.replace("{辖区区域1}", "、".join(towns) if towns else "全县")
            if needs_double_region:
                message_body = message_body.replace("{辖区区域2}", "、".join(towns_2) if towns_2 else "、".join(towns) if towns else "全县")
            
            if "X小时" in message_body:
                message_body = message_body.replace("X小时", str(extra_data.get("短短信时间", "")) + "小时")
            if "X小时内" in message_body:
                message_body = message_body.replace("X小时内", str(extra_data.get("短短信时间", "")) + "小时内")
            if "{XX}" in message_body:
                message_body = message_body.replace("{XX}", extra_data.get("影响区域", ""))
            
            final_message = message_body

        elif sms_type == "长短信":
            message_body = template.get("主体", "")
            
            message_body = message_body.replace("X县", "平乐县")
            message_body = message_body.replace("X日", day_part)
            message_body = message_body.replace("X时X分", time_display)
            
            if real_template_type == "解除":
                message_body = message_body.replace("{预警级别}", level_key if 'level_key' in dir() else level)
                for key in ["云团状态", "影响状态", "过去时长", "实际影响区域", "降雨范围", "局地降雨范围", "最大降雨区域", "最大降雨量"]:
                    message_body = message_body.replace(f"{{{key}}}", str(extra_data.get(key, "")))
            else:
                # 区域替换逻辑 - 支持双区域
                message_body = message_body.replace("{辖区区域1}", "、".join(towns) if towns else "全县")
                if needs_double_region:
                    message_body = message_body.replace("{辖区区域2}", "、".join(towns_2) if towns_2 else "、".join(towns) if towns else "全县")
                
                message_body = message_body.replace("X1", str(extra_data.get("过去时长", "")))
                message_body = message_body.replace("Y1", str(extra_data.get("已出现降雨", "")))
                message_body = message_body.replace("Y2", str(extra_data.get("未来降雨", "")))
                message_body = message_body.replace("XX", str(extra_data.get("未来时长", "")))
                
                message_body = message_body.replace("{伴随天气}", extra_data.get("伴随天气", ""))
                message_body = message_body.replace("{移向}", extra_data.get("移向", ""))
                message_body = message_body.replace("{强度变化趋势}", extra_data.get("强度变化趋势", ""))
            
            final_message = message_body
            
            upgrade_prompt = template.get("升级提示", "")
            if upgrade_prompt and extra_data.get("升级提示", False):
                final_message += upgrade_prompt
            
            risk_type = extra_data.get("风险类型", "")
            if risk_type and "风险提示" in template:
                risk_text = template["风险提示"].get(risk_type, "")
                if risk_text:
                    final_message += risk_text
            
            ending = template.get("结尾", "")
            if ending:
                final_message += ending

        return final_message

    except Exception as e:
        return f"生成短信时发生错误：{e}"

def update_p3_content():
    """生成暴雨短信内容 - 包含参数校验"""
    try:
        required_keys = ['p3_level', 'p3_template_type', 'selected_towns']
        if any(key not in st.session_state for key in required_keys):
            st.error("关键参数未初始化，请检查页面状态。")
            st.session_state.p3_generation_success = False
            return
        
        # 获取时间参数
        p3_selected_date = f"{st.session_state.p3_sel_year}年{st.session_state.p3_sel_month:02d}月{st.session_state.p3_sel_day:02d}日"
        p3_selected_time = f"{st.session_state.p3_sel_hour:02d}时{st.session_state.p3_sel_minute:02d}分"
        
        # 收集额外数据
        extra_data_keys = ["过去时长", "已出现降雨", "未来时长", "未来降雨", "短短信时间", 
                  "伴随天气", "移向", "强度变化趋势", "风险类型", "升级提示",
                  "云团状态", "影响状态", "实际影响区域", "降雨范围", "最大降雨区域", "最大降雨量"]
        current_extra_data = {}
        for key in extra_data_keys:
            state_key = f'p3_extra_data_{key}'
            current_extra_data[key] = st.session_state.get(state_key, "")
        
        # 参数校验
        try:
            y1_value = float(current_extra_data.get("已出现降雨", 0))
            y2_value = float(current_extra_data.get("未来降雨", 0))
            x1_value = float(current_extra_data.get("过去时长", 0))
            xx_value = float(current_extra_data.get("未来时长", 0))
        except (ValueError, TypeError):
            y1_value = 0
            y2_value = 0
            x1_value = 0
            xx_value = 0
        
        template_type = st.session_state.p3_template_type
        level = st.session_state.p3_level
        
        # 执行校验
        is_valid, warnings = validate_all_values(y1_value, y2_value, x1_value, xx_value, template_type, level)
        
        # 存储校验结果用于显示
        st.session_state.p3_validation_warnings = warnings
        
        # 生成短短信和长短信（无论校验是否通过都生成）
        short_sms_text = generate_message(
            st.session_state.p3_level, 
            st.session_state.p3_template_type, 
            "短短信",
            st.session_state.selected_towns,
            p3_selected_date,
            p3_selected_time,
            current_extra_data,
            st.session_state.get('selected_towns_2', [])
        )
        
        long_sms_text = generate_message(
            st.session_state.p3_level, 
            st.session_state.p3_template_type, 
            "长短信",
            st.session_state.selected_towns,
            p3_selected_date,
            p3_selected_time,
            current_extra_data,
            st.session_state.get('selected_towns_2', [])
        )
        
        st.session_state.p3_short_sms = short_sms_text
        st.session_state.p3_long_sms = long_sms_text
        st.session_state.p3_generation_success = True
        
    except Exception as e:
        error_msg = f"生成短信时发生错误：{str(e)}"
        st.session_state.p3_short_sms = error_msg
        st.session_state.p3_long_sms = error_msg
        st.session_state.p3_generation_success = False
        st.session_state.p3_validation_warnings = []

# ==============================================================================
# 7. STREAMLIT PAGES (页面函数)
# ==============================================================================

def create_main_page():
    st.title("🌧️ 气象预警发布系统 (主页)")
    
    st.markdown("#### 发布时间选择")

    now = datetime.datetime.now()
    
    required_states = [
        'p1_generated_content', 'p1_weather_type', 
        'p1_weather_level', 'p1_template_type'
    ]
    
    for state in required_states:
        if state not in st.session_state:
            initialize_session_state()
            st.rerun()
            return
    
    col_y, col_m, col_d, col_h, col_mn = st.columns(5)
    
    with col_y:
        st.selectbox("年份", options=list(range(now.year, now.year + 6)), index=0, key='sel_year', on_change=update_datetime_state)
    with col_m:
        st.selectbox("月份", options=list(range(1, 13)), format_func=lambda x: f"{x:02d}", index=now.month-1, key='sel_month', on_change=update_datetime_state)
    with col_d:
        default_day_index = now.day - 1 if 1 <= now.day <= 31 else 0
        st.selectbox("日期", options=list(range(1, 32)), format_func=lambda x: f"{x:02d}", index=default_day_index, key='sel_day', on_change=update_datetime_state)
    with col_h:
        st.selectbox("小时", options=list(range(0, 24)), format_func=lambda x: f"{x:02d}", index=now.hour, key='sel_hour', on_change=update_datetime_state)
    with col_mn:
        st.selectbox("分钟", options=list(range(0, 60)), format_func=lambda x: f"{x:02d}", index=now.minute, key='sel_minute', on_change=update_datetime_state)

    st.divider()

    st.markdown("#### 气象灾害预警信号选择")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.selectbox(
            "灾害类别:", 
            options=list(WEATHER_LEVELS.keys()), 
            key='p1_weather_type',
        )

    p1_levels = get_p1_levels()
    if 'p1_weather_level' not in st.session_state or st.session_state.p1_weather_level not in p1_levels:
        st.session_state.p1_weather_level = p1_levels[0] if p1_levels else ""

    with col2:
        st.selectbox(
            "预警等级:", 
            options=p1_levels,
            key='p1_weather_level',
        )

    p1_template_types = get_p1_template_types(st.session_state.p1_weather_type, st.session_state.p1_weather_level)
    if 'p1_template_type' not in st.session_state or st.session_state.p1_template_type not in p1_template_types:
        st.session_state.p1_template_type = p1_template_types[0] if p1_template_types else ""

    with col3:
        st.selectbox(
            "预警用语类型:",
            options=p1_template_types,
            key='p1_template_type',
        )

    st.markdown("#### 预警内容生成与预览")
    st.button("生成预警内容", on_click=generate_weather_content, type="primary", key="generate_p1_btn")

    show_copyable_preview(st.session_state.p1_generated_content)

    st.markdown("#### 业务人员内容纠错")
    
    default_correction_text = st.session_state.get('p1_generated_content', '平乐县气象台发布了雷电黄色预警，的得注意防范。')
    input_text = st.text_area("输入待纠错文本", value=default_correction_text, height=150, key='p1_correction_input')
    
    corrected_output_placeholder = st.empty()

    if st.button("执行纠错", key="run_correction"):
        reference = st.session_state.get('p1_last_clean_text', '')
        if reference and _is_minor_edit(input_text, reference):
            corrected_result = f"[纠错成功]\n{reference}"
        else:
            corrected_result = correct_text(input_text)
        corrected_output_placeholder.text_area("纠错结果", corrected_result, height=150)
    else:
        corrected_output_placeholder.text_area("纠错结果", "点击下方按钮执行纠错。", height=150)

    st.divider()

    st.button("暴雨短信工具", on_click=go_to_third_page, use_container_width=True)

def create_third_page():
    """暴雨预警短信生成工具页面"""
    st.title("💬 暴雨预警短信生成工具")
    
    # --- 发布时间设置区域 ---
    st.markdown("#### 发布时间设置")
    now = datetime.datetime.now()
    
    col_y, col_m, col_d, col_h, col_mn = st.columns(5)
    
    with col_y:
        st.selectbox("年份", options=list(range(now.year, now.year + 6)), index=0, key='p3_sel_year')
    with col_m:
        st.selectbox("月份", options=list(range(1, 13)), format_func=lambda x: f"{x:02d}", 
                    index=now.month-1, key='p3_sel_month')
    with col_d:
        default_day_index = now.day - 1 if 1 <= now.day <= 31 else 0
        st.selectbox("日期", options=list(range(1, 32)), format_func=lambda x: f"{x:02d}", 
                    index=default_day_index, key='p3_sel_day')
    with col_h:
        st.selectbox("小时", options=list(range(0, 24)), format_func=lambda x: f"{x:02d}", 
                    index=now.hour, key='p3_sel_hour')
    with col_mn:
        st.selectbox("分钟", options=list(range(0, 60)), format_func=lambda x: f"{x:02d}", 
                    index=now.minute, key='p3_sel_minute')
    
    st.divider()

    # --- 预警信号选择 ---
    st.markdown("#### 预警信号选择")
    
    col_p3_1, col_p3_2 = st.columns(2)

    template_type_options = ["提前", "过程", "实况", "实况趋减", "继续发布", "解除", "预警升级", "预警降级"]
    with col_p3_2:
        p3_template_type = st.selectbox("预警类型:", options=template_type_options, 
                                       index=template_type_options.index("继续发布"), 
                                       key='p3_template_type')

    # 动态等级选项
    if p3_template_type == "预警升级":
        level_options = ["黄升橙色", "黄升红色", "橙升红色"]
    elif p3_template_type == "预警降级":
        level_options = ["橙降黄色", "红降黄色", "红降橙色"]
    else:
        level_options = ["黄色", "橙色", "红色"]
        
    if 'p3_level' not in st.session_state or st.session_state.p3_level not in level_options:
        st.session_state.p3_level = level_options[0]

    with col_p3_1:
        st.selectbox("预警等级:", options=level_options, key='p3_level')

    # ==========================================================================
    # 乡镇选择功能
    # ==========================================================================
    st.markdown("#### 乡镇选择")

    current_template_type = st.session_state.p3_template_type
    needs_double_region = current_template_type in DOUBLE_REGION_TEMPLATES
    st.session_state.show_second_region = needs_double_region

    # 第一组乡镇选择（当前影响区域）
    st.info("📍 当前已受影响区域（区域1）")

    col_town_1, col_town_2, col_town_3 = st.columns(3)

    with col_town_1:
        for i in range(min(4, len(TOWN_NAMES))):
            town = TOWN_NAMES[i]
            checkbox_key = f"town_{town}"
            is_currently_checked = town in st.session_state.selected_towns
            checkbox_state = st.checkbox(
                town, 
                value=is_currently_checked, 
                key=checkbox_key
            )
            if checkbox_state and not is_currently_checked:
                if town not in st.session_state.selected_towns:
                    st.session_state.selected_towns.append(town)
            elif not checkbox_state and is_currently_checked:
                if town in st.session_state.selected_towns:
                    st.session_state.selected_towns.remove(town)

    with col_town_2:
        for i in range(4, min(8, len(TOWN_NAMES))):
            town = TOWN_NAMES[i]
            checkbox_key = f"town_{town}"
            is_currently_checked = town in st.session_state.selected_towns
            checkbox_state = st.checkbox(
                town, 
                value=is_currently_checked, 
                key=checkbox_key
            )
            if checkbox_state and not is_currently_checked:
                if town not in st.session_state.selected_towns:
                    st.session_state.selected_towns.append(town)
            elif not checkbox_state and is_currently_checked:
                if town in st.session_state.selected_towns:
                    st.session_state.selected_towns.remove(town)

    with col_town_3:
        for i in range(8, len(TOWN_NAMES)):
            town = TOWN_NAMES[i]
            checkbox_key = f"town_{town}"
            is_currently_checked = town in st.session_state.selected_towns
            checkbox_state = st.checkbox(
                town, 
                value=is_currently_checked, 
                key=checkbox_key
            )
            if checkbox_state and not is_currently_checked:
                if town not in st.session_state.selected_towns:
                    st.session_state.selected_towns.append(town)
            elif not checkbox_state and is_currently_checked:
                if town in st.session_state.selected_towns:
                    st.session_state.selected_towns.remove(town)

    # 动态显示第二组乡镇选择（区域2）
    if st.session_state.show_second_region:
        st.markdown("---")
        st.info("🔮 未来可能影响区域（区域2）")
        
        col_town2_1, col_town2_2, col_town2_3 = st.columns(3)
        
        with col_town2_1:
            for i in range(min(4, len(TOWN_NAMES))):
                town = TOWN_NAMES[i]
                checkbox_key_2 = f"town_checkbox_2_{town}"
                current_selected_2 = st.session_state.selected_towns_2
                is_currently_checked_2 = town in current_selected_2
                checkbox_state_2 = st.checkbox(
                    f"{town} (区域2)", 
                    value=is_currently_checked_2, 
                    key=checkbox_key_2
                )
                if checkbox_state_2 and not is_currently_checked_2:
                    if town not in st.session_state.selected_towns_2:
                        st.session_state.selected_towns_2.append(town)
                elif not checkbox_state_2 and is_currently_checked_2:
                    if town in st.session_state.selected_towns_2:
                        st.session_state.selected_towns_2.remove(town)
        
        with col_town2_2:
            for i in range(4, min(8, len(TOWN_NAMES))):
                town = TOWN_NAMES[i]
                checkbox_key_2 = f"town_checkbox_2_{town}"
                current_selected_2 = st.session_state.selected_towns_2
                is_currently_checked_2 = town in current_selected_2
                checkbox_state_2 = st.checkbox(
                    f"{town} (区域2)", 
                    value=is_currently_checked_2, 
                    key=checkbox_key_2
                )
                if checkbox_state_2 and not is_currently_checked_2:
                    if town not in st.session_state.selected_towns_2:
                        st.session_state.selected_towns_2.append(town)
                elif not checkbox_state_2 and is_currently_checked_2:
                    if town in st.session_state.selected_towns_2:
                        st.session_state.selected_towns_2.remove(town)
        
        with col_town2_3:
            for i in range(8, len(TOWN_NAMES)):
                town = TOWN_NAMES[i]
                checkbox_key_2 = f"town_checkbox_2_{town}"
                current_selected_2 = st.session_state.selected_towns_2
                is_currently_checked_2 = town in current_selected_2
                checkbox_state_2 = st.checkbox(
                    f"{town} (区域2)", 
                    value=is_currently_checked_2, 
                    key=checkbox_key_2
                )
                if checkbox_state_2 and not is_currently_checked_2:
                    if town not in st.session_state.selected_towns_2:
                        st.session_state.selected_towns_2.append(town)
                elif not checkbox_state_2 and is_currently_checked_2:
                    if town in st.session_state.selected_towns_2:
                        st.session_state.selected_towns_2.remove(town)
    else:
        # 非双区域模式时，保持区域2与区域1同步
        st.session_state.selected_towns_2 = st.session_state.selected_towns.copy()

    st.markdown("---")

    if st.session_state.get('force_rerun', False):
        st.session_state.force_rerun = False
        st.rerun()

    col_btn_1, col_btn_2, col_btn_3, col_btn_4 = st.columns(4)

    with col_btn_1:
        st.button(
            "✅ 全选区域1", 
            use_container_width=True, 
            key="btn_select_all_region_1",
            on_click=select_all_region_1,
            type="secondary"
        )

    with col_btn_2:
        st.button(
            "❌ 清空区域1", 
            use_container_width=True, 
            key="btn_deselect_all_region_1",
            on_click=deselect_all_region_1,
            type="secondary"
        )

    if st.session_state.show_second_region:
        with col_btn_3:
            st.button(
                "✅ 全选区域2", 
                use_container_width=True, 
                key="btn_select_all_region_2",
                on_click=select_all_region_2,
                type="secondary"
            )
        
        with col_btn_4:
            st.button(
                "❌ 清空区域2", 
                use_container_width=True, 
                key="btn_deselect_all_region_2",
                on_click=deselect_all_region_2,
                type="secondary"
            )

    if st.session_state.selected_towns:
        st.success(f"✅ 区域1已选中 {len(st.session_state.selected_towns)} 个乡镇：{', '.join(st.session_state.selected_towns)}")

    if st.session_state.show_second_region and st.session_state.selected_towns_2:
        st.info(f"🔮 区域2已选中 {len(st.session_state.selected_towns_2)} 个乡镇：{', '.join(st.session_state.selected_towns_2)}")

    # --- 额外信息输入区域 ---
    st.markdown("---")
    st.markdown("#### 额外信息输入")
    
    # 获取当前预警类型和等级对应的校验规则
    current_template_type = st.session_state.p3_template_type
    current_level = st.session_state.p3_level
    rules = get_current_validation_rules(current_template_type, current_level)
    
    with st.expander("常规参数与风险提示", expanded=True):
        # 显示当前预警类型的参数范围要求（醒目信息框）
        st.markdown(f"**📋 当前预警类型 [{current_template_type} - {current_level}] 的参数要求：**")
        
        # 构建范围提示信息
        param_hints = []
        if rules.get("X1") is not None:
            param_hints.append(f"**X1(过去时长):** {get_range_description(rules.get('X1'))}")
        if rules.get("Y1") is not None:
            param_hints.append(f"**Y1(已出现降雨):** {get_range_description(rules.get('Y1'))}")
        if rules.get("XX") is not None:
            param_hints.append(f"**XX(未来时长):** {get_range_description(rules.get('XX'))}")
        if rules.get("Y2") is not None:
            param_hints.append(f"**Y2(未来降雨):** {get_range_description(rules.get('Y2'))}")
        
        if param_hints:
            st.info(" | ".join(param_hints))
        else:
            st.info("当前预警类型无特殊参数限制")
        
        st.markdown("---")
        
        col_r1, col_r2, col_r3 = st.columns(3)
        
        # 获取简短范围描述用于标签
        x1_short = get_short_range_description(rules.get("X1"))
        y1_short = get_short_range_description(rules.get("Y1"))
        xx_short = get_short_range_description(rules.get("XX"))
        y2_short = get_short_range_description(rules.get("Y2"))
        
        with col_r1:
            st.text_input(
                f"过去时长 X1 {x1_short}:", 
                value=st.session_state.p3_extra_data_过去时长, 
                key='p3_extra_data_过去时长', 
                help=f"对应模板中的 X1。{get_range_description(rules.get('X1'))}"
            )
            st.text_input(
                f"已出现降雨 Y1 {y1_short}:", 
                value=st.session_state.p3_extra_data_已出现降雨,
                key='p3_extra_data_已出现降雨', 
                help=f"对应模板中的 Y1。{get_range_description(rules.get('Y1'))}"
            )
            
        with col_r2:
            st.text_input(
                f"未来时长 XX {xx_short}:", 
                value=st.session_state.p3_extra_data_未来时长,
                key='p3_extra_data_未来时长', 
                help=f"对应模板中的 XX。{get_range_description(rules.get('XX'))}"
            )
            st.text_input(
                f"未来降雨 Y2 {y2_short}:", 
                value=st.session_state.p3_extra_data_未来降雨,
                key='p3_extra_data_未来降雨', 
                help=f"对应模板中的 Y2。{get_range_description(rules.get('Y2'))}"
            )
            st.text_input(
                "短短信时间(X小时):", 
                value=st.session_state.p3_extra_data_短短信时间,
                key='p3_extra_data_短短信时间', 
                help="对应模板中的 X小时/X小时内"
            )
            
        with col_r3:
            st.text_input(
                "伴随天气:", 
                value=st.session_state.p3_extra_data_伴随天气,
                key='p3_extra_data_伴随天气', 
                help="对应模板中的 {伴随天气}"
            )
            st.text_input(
                "云团移向:", 
                value=st.session_state.p3_extra_data_移向,
                key='p3_extra_data_移向', 
                help="对应模板中的 {移向}"
            )
            st.text_input(
                "强度变化趋势:", 
                value=st.session_state.p3_extra_data_强度变化趋势,
                key='p3_extra_data_强度变化趋势', 
                help="对应模板中的 {强度变化趋势}"
            )
            
            risk_type_options = ["城乡积涝", "山洪地质灾害", "其他（自定义）"]
            current_risk = st.session_state.p3_extra_data_风险类型
            
            selected_index = risk_type_options.index(current_risk) if current_risk in risk_type_options else 2
            
            selected_risk_type = st.selectbox(
                "风险类型:", 
                options=risk_type_options,
                index=selected_index,
                key='p3_risk_type_select'
            )
            
            if selected_risk_type == "其他（自定义）":
                custom_value = current_risk if current_risk not in risk_type_options else ""
                custom_risk = st.text_input(
                    "请输入自定义风险类型:",
                    value=custom_value,
                    key='p3_custom_risk_type'
                )
                if custom_risk:
                    st.session_state.p3_extra_data_风险类型 = custom_risk
            else:
                st.session_state.p3_extra_data_风险类型 = selected_risk_type
            
            st.checkbox(
                "包含升级提示", 
                value=st.session_state.p3_extra_data_升级提示, 
                key='p3_extra_data_升级提示',
                help="是否添加模板中的升级提示内容"
            )

    # 仅在解除预警时显示特殊参数
    if st.session_state.p3_template_type == "解除":
        with st.expander("解除预警参数", expanded=True):
            col_c1, col_c2 = st.columns(2)
            
            with col_c1:
                st.selectbox(
                    "云团状态:", 
                    options=["强降雨云团已远离", "强降雨云团已明显减弱"], 
                    key='p3_extra_data_云团状态'
                )
                st.text_input(
                    "实际影响区域:", 
                    value=st.session_state.p3_extra_data_实际影响区域, 
                    key='p3_extra_data_实际影响区域'
                )
                st.text_input(
                    "最大降雨区域:", 
                    value=st.session_state.p3_extra_data_最大降雨区域, 
                    key='p3_extra_data_最大降雨区域'
                )
            
            with col_c2:
                st.selectbox(
                    "影响状态:", 
                    options=["结束", "减弱"], 
                    key='p3_extra_data_影响状态'
                )
                st.text_input(
                    "降雨范围:", 
                    value=st.session_state.p3_extra_data_降雨范围, 
                    key='p3_extra_data_降雨范围'
                )
                st.text_input(
                    "最大降雨量:", 
                    value=st.session_state.p3_extra_data_最大降雨量, 
                    key='p3_extra_data_最大降雨量'
                )

    # ==========================================================================
    # 短信生成和显示
    # ==========================================================================
    st.divider()

    if st.button("生成暴雨短信", type="primary", use_container_width=True, key="generate_p3_final"):
        update_p3_content()
        
        # 显示校验警告（如果有）
        warnings = st.session_state.get('p3_validation_warnings', [])
        if warnings:
            for warning in warnings:
                st.warning(warning)
            st.info("⚠️ 部分参数不在建议范围内，短信已生成，请核实数据后使用。")
        else:
            st.success("✅ 短信生成成功！参数校验通过。")
        
        st.rerun()

    # 短信显示部分
    st.markdown("#### 短信内容预览")

    col_sms_short, col_sms_long = st.columns(2)

    with col_sms_short:
        st.markdown("##### 📱 短短信")
        show_copyable_preview(
            st.session_state.get('p3_short_sms', '短短信内容将显示在这里。'),
            ta_height=120
        )

    with col_sms_long:
        st.markdown("##### 📄 长短信")
        show_copyable_preview(
            st.session_state.get('p3_long_sms', '长短信内容将显示在这里。'),
            ta_height=200
        )
    
    st.divider()
    st.button("返回主页", on_click=go_to_main_page, type="secondary")
 
# ==============================================================================
# 8. MAIN APP ENTRY POINT (主程序入口)
# ==============================================================================

def app():
    st.set_page_config(layout="wide", page_title="气象预警发布系统")
    
    initialize_session_state()
    
    if st.session_state.get('debug_mode', False):
        st.sidebar.write("当前状态键:", list(st.session_state.keys()))
    
    if st.session_state.page == 'main_page':
        create_main_page()
    elif st.session_state.page == 'third_page':
        create_third_page()
    
    st.sidebar.markdown("---")
    st.sidebar.caption("版本 1.46.0 - 新增X1/XX范围校验，优化范围提示显示")

if __name__ == "__main__":
    app()

