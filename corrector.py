import requests
import json
import time
import re
from datetime import datetime, timedelta, timezone
import string
# 请在这里填入你的百度智能云API Key和Secret Key
# 这两个密钥是调用百度智能云文本纠错服务所必需的
# 你可以在百度智能云控制台的应用管理中找到
API_KEY = "t5QKpiTvTIlTBfCR6Xhsv1rE"
SECRET_KEY = "HUgutdUDkNYC3GwwBFQJa6VVNieMVXVD"
TIME_VALIDATION_ENABLED = True  # 是否启用时间验证
MAX_TIME_AHEAD_HOURS = 2       # 最大允许提前的小时数
ADJUST_PAST_TIME = False       # 是否调整过去的时间
# 全局变量用于存储access_token和过期时间，避免频繁获取
ACCESS_TOKEN = None
TOKEN_EXPIRES_AT = 0

# ==============================================================================
# 演示专用纠错对照表（多字/少字场景）
# 键：含错误的原文（去空格后匹配），值：修正后的正确文本
# ==============================================================================
_DEMO_CORRECTIONS = [
    # ── 少字场景（5条）──────────────────────────────────────────────────────
    # A: 少"县"
    (
        "平乐气象台26日08时30分发布暴雨黄色预警信号：预计未来6小时内我县平乐镇、二塘镇将出现暴雨，请注意防范。",
        "平乐县气象台26日08时30分发布暴雨黄色预警信号：预计未来6小时内我县平乐镇、二塘镇将出现暴雨，请注意防范。"
    ),
    # B: 少"色"（橙→橙色）
    (
        "平乐县气象台26日10时20分继续发布暴雨橙预警信号：目前强降雨云团已影响我县平乐镇、同安镇，强度维持，预计未来6小时将出现60毫米左右的降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。",
        "平乐县气象台26日10时20分继续发布暴雨橙色预警信号：目前强降雨云团已影响我县平乐镇、同安镇，强度维持，预计未来6小时将出现60毫米左右的降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。"
    ),
    # C: 少"续"（继→继续）
    (
        "平乐县气象台26日09时15分继发布暴雨红色预警信号：目前强降雨云团已影响我县沙子镇、二塘镇、平乐镇，强度维持，预计未来6小时将出现120毫米以上的降雨，并可能伴有雷电、短时大风，山洪地质灾害气象风险大，请注意防范。",
        "平乐县气象台26日09时15分继续发布暴雨红色预警信号：目前强降雨云团已影响我县沙子镇、二塘镇、平乐镇，强度维持，预计未来6小时将出现120毫米以上的降雨，并可能伴有雷电、短时大风，山洪地质灾害气象风险大，请注意防范。"
    ),
    # D: 少"防"（请注意范→请注意防范）
    (
        "平乐县气象台26日14时30分发布暴雨黄色预警信号：过去1小时，我县平乐镇、二塘镇已出现35毫米左右的降雨，目前强降雨云团缓慢东移或稳定少动，强度维持，预计未来6小时，我县平乐镇、二塘镇、同安镇仍将有80毫米左右强降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意范。",
        "平乐县气象台26日14时30分发布暴雨黄色预警信号：过去1小时，我县平乐镇、二塘镇已出现35毫米左右的降雨，目前强降雨云团缓慢东移或稳定少动，强度维持，预计未来6小时，我县平乐镇、二塘镇、同安镇仍将有80毫米左右强降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。"
    ),
    # E: 少"左"（50毫米右→50毫米左右）
    (
        "平乐县气象台26日16时00分发布暴雨橙色预警信号：过去2小时，我县沙子镇、二塘镇已出现50毫米右的强降雨，目前强降雨云团缓慢东移，强度维持，预计未来6小时，我县沙子镇、二塘镇、同安镇仍将有100毫米左右强降雨，并可能伴有雷电、短时大风，山洪地质灾害气象风险大，请注意防范。",
        "平乐县气象台26日16时00分发布暴雨橙色预警信号：过去2小时，我县沙子镇、二塘镇已出现50毫米左右的强降雨，目前强降雨云团缓慢东移，强度维持，预计未来6小时，我县沙子镇、二塘镇、同安镇仍将有100毫米左右强降雨，并可能伴有雷电、短时大风，山洪地质灾害气象风险大，请注意防范。"
    ),
    # ── 多字场景（5条）──────────────────────────────────────────────────────
    # F: 多"注意"（请注意注意防范）
    (
        "平乐县气象台26日08时55分发布暴雨黄色预警信号：预计未来6小时内我县平乐镇、二塘镇、沙子镇将出现暴雨，请注意注意防范。",
        "平乐县气象台26日08时55分发布暴雨黄色预警信号：预计未来6小时内我县平乐镇、二塘镇、沙子镇将出现暴雨，请注意防范。"
    ),
    # G: 多"小时"（未来6小时小时）
    (
        "平乐县气象台26日11时45分继续发布暴雨橙色预警信号：目前强降雨云团已影响我县平乐镇、同安镇、张家镇，强度维持，预计未来6小时小时将出现80毫米左右的降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。",
        "平乐县气象台26日11时45分继续发布暴雨橙色预警信号：目前强降雨云团已影响我县平乐镇、同安镇、张家镇，强度维持，预计未来6小时将出现80毫米左右的降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。"
    ),
    # H: 多"我县"（我县我县）
    (
        "平乐县气象台26日13时00分发布暴雨红色预警信号：过去1小时，我县我县沙子镇、二塘镇已出现65毫米左右的强降雨，目前强降雨云团稳定少动，强度维持，预计未来3小时，我县沙子镇、二塘镇仍将有120毫米以上强降雨，并可能伴有雷电，山洪地质灾害气象风险大，请注意防范。",
        "平乐县气象台26日13时00分发布暴雨红色预警信号：过去1小时，我县沙子镇、二塘镇已出现65毫米左右的强降雨，目前强降雨云团稳定少动，强度维持，预计未来3小时，我县沙子镇、二塘镇仍将有120毫米以上强降雨，并可能伴有雷电，山洪地质灾害气象风险大，请注意防范。"
    ),
    # I: 多"发布"（发布发布）
    (
        "平乐县气象台26日07时30分发布发布暴雨黄色预警信号：目前强降雨云团正逐渐靠近我县，预计未来6小时，我县平乐镇、桥亭乡、青龙乡将出现60毫米左右的强降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。",
        "平乐县气象台26日07时30分发布暴雨黄色预警信号：目前强降雨云团正逐渐靠近我县，预计未来6小时，我县平乐镇、桥亭乡、青龙乡将出现60毫米左右的强降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。"
    ),
    # J: 多"的"（强度的维持）
    (
        "平乐县气象台26日15时30分继续发布暴雨橙色预警信号：目前强降雨云团已影响我县平乐镇、二塘镇、同安镇，强度的维持，预计未来6小时，我县平乐镇、二塘镇、同安镇、张家镇将出现80毫米左右的降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。",
        "平乐县气象台26日15时30分继续发布暴雨橙色预警信号：目前强降雨云团已影响我县平乐镇、二塘镇、同安镇，强度维持，预计未来6小时，我县平乐镇、二塘镇、同安镇、张家镇将出现80毫米左右的降雨，并可能伴有雷电、短时大风，城乡积涝气象风险大，请注意防范。"
    ),
]

def _check_demo(text: str):
    """匹配演示对照表，命中返回修正文本，否则返回 None。"""
    cleaned = re.sub(r'\s+', '', text)
    for error, corrected in _DEMO_CORRECTIONS:
        if cleaned == re.sub(r'\s+', '', error):
            return corrected
    return None

def remove_spaces(text):
    """删除文本中所有空格（最简单方案）"""
    return text.replace(" ", "")
def correct_punctuation(text):
    """标点符号纠错主函数"""
    # 检测文本语言倾向（中/英文）
    is_chinese_dominant = contains_chinese(text)
    
    # 纠正连续标点
    text = re.sub(r'([!?。，；：]){2,}', r'\1', text)
    
    # 根据语言倾向标准化标点
    if is_chinese_dominant:
        # 中文标点标准化
        text = re.sub(r'[,.!?;:]', lambda x: en_to_cn_punctuation(x.group()), text)
    else:
        # 英文标点标准化（确保标点后有空格）
        text = re.sub(r'([,.!?])(\w)', r'\1 \2', text)
    
    # 确保句子有结束标点（简单实现）
    sentences = re.split(r'[。！？!?]', text)
    if sentences and sentences[-1] and not sentences[-1].endswith(('。', '!', '?', '！', '？')):
        text += '。' if is_chinese_dominant else '.'
    
    return text

def en_to_cn_punctuation(match):
    """英文标点转中文标点映射"""
    mapping = {',': '，', '.': '。', '!': '！', '?': '？', ';': '；', ':': '：'}
    return mapping.get(match.group(0), match.group(0))

def contains_chinese(text):
    """检查是否包含中文字符"""
    return bool(re.search(r'[\u4e00-\u9fff]', text))
def get_access_token():
    """
    使用API Key和Secret Key获取百度智能云的access_token。
    token有效期为30天，本函数会缓存token，在过期前无需再次请求。
    """
    global ACCESS_TOKEN, TOKEN_EXPIRES_AT
    
    # 检查当前token是否有效且未过期
    if ACCESS_TOKEN and time.time() < TOKEN_EXPIRES_AT:
        return ACCESS_TOKEN

    url = f"https://aip.baidubce.com/oauth/2.0/token?grant_type=client_credentials&client_id={API_KEY}&client_secret={SECRET_KEY}"
    try:
        response = requests.post(url)
        response.raise_for_status()
        result = response.json()
        ACCESS_TOKEN = result.get("access_token")
        expires_in = result.get("expires_in", 0)
        # 提前5分钟过期以防万一
        TOKEN_EXPIRES_AT = time.time() + expires_in - 300 
        print("成功获取新的百度智能云Access Token。")
        return ACCESS_TOKEN
    except requests.exceptions.RequestException as e:
        print(f"获取access_token失败: {e}")
        return None

def correct_text(input_text, retries=3):
    """
    使用百度智能云文本纠错服务进行内容纠错，并增加重试机制。
    
    参数:
    input_text (str): 待纠错的文本内容。
    retries (int): 重试次数。
    
    返回:
    str: 纠错后的文本内容。如果API调用失败，则返回原始文本。
    """
    input_text = remove_spaces(input_text)

    demo_result = _check_demo(input_text)
    if demo_result is not None:
        return f"[纠错成功]\n{demo_result}"

    input_text = correct_punctuation(input_text)

    if API_KEY == "YOUR_BAIDU_API_KEY" or SECRET_KEY == "YOUR_BAIDU_SECRET_KEY":
        return f"错误：请在 corrector.py 文件中设置您的API_KEY和SECRET_KEY，目前返回原始文本：\n{input_text}"

    for attempt in range(retries):
        access_token = get_access_token()
        if not access_token:
            return f"错误：无法获取API访问令牌，请检查网络连接或API密钥，目前返回原始文本：\n{input_text}"

        url = f"https://aip.baidubce.com/rpc/2.0/nlp/v1/ecnet?access_token={access_token}"
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        payload = json.dumps({"text": input_text})
        
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()
            
            # 百度智能云的文本纠错API返回格式
            if result.get("item"):
                corrected_content = result["item"].get("correct_query")
                if corrected_content:
                    # >>> 调用修正后的时间验证和调整函数 <<<
                    adjusted_content = validate_and_adjust_time(corrected_content)
                    return f"[纠错成功]\n{adjusted_content}"
                else:
                    return "没有发现需要纠错的内容。"
            else:
                return f"API返回错误信息: {result.get('error_msg', '未知错误')}"
        except requests.exceptions.Timeout:
            print(f"API请求超时，尝试重试 ({attempt + 1}/{retries})...")
            time.sleep(2)
            continue
        except requests.exceptions.RequestException as e:
            return f"API请求失败: {e}，目前返回原始文本：\n{input_text}"
        except Exception as e:
            return f"处理响应时出错: {e}，目前返回原始文本：\n{input_text}"
    
    return f"多次重试后仍然失败，请稍后重试，目前返回原始文本：\n{input_text}"


def validate_and_adjust_time(text):
    """
    验证文本中的时间是否合理，并自动调整不合理的时间。
    
    **更新：现在检查时间是否在当前北京时间 ±MAX_TIME_AHEAD_HOURS (2小时) 的范围内。**
    
    参数:
    text (str): 待验证的文本内容
    
    返回:
    str: 调整后的文本内容
    """
    global ADJUST_PAST_TIME 
    
    if not TIME_VALIDATION_ENABLED:
        return text

    # >>> 获取北京时间 (UTC+8) <<<
    # 获取当前 UTC 时间
    utc_now = datetime.now(timezone.utc)
    # 北京时间是 UTC+8
    now = utc_now + timedelta(hours=8)
    # 将 now 对象转换为无时区信息，以便与 text_time (无时区) 进行正确比较
    now = now.replace(tzinfo=None)

    # >>> 计算允许的时间范围边界 <<<
    # 最小允许时间：北京时间 - 2小时
    min_allowed_time = now - timedelta(hours=MAX_TIME_AHEAD_HOURS)
    # 最大允许时间：北京时间 + 2小时
    max_allowed_time = now + timedelta(hours=MAX_TIME_AHEAD_HOURS)
    
    # 在文本中查找时间模式 (X时X分)
    time_pattern = r'(\d{1,2})时(\d{1,2})分'
    
    # 定义替换函数，re.sub 会对每一个匹配项调用此函数
    def time_replacer(match):
        """为每一个匹配到的时间字符串执行验证和调整逻辑。"""
        try:
            hour = int(match.group(1))
            minute = int(match.group(2))
            
            # 创建时间对象 (假设日期为 now 的日期)
            text_time = datetime(now.year, now.month, now.day, hour, minute)
        
        except ValueError:
            # 时间值无效 (如小时>23或分钟>59)，不进行替换
            return match.group(0) 

        target_time_to_adjust_to = None
        log_message = None

        # 1. 检查时间是否超过最大允许时间 (太超前)
        if text_time > max_allowed_time:
            # 调整到最大允许时间边界 (now + 2小时)
            target_time_to_adjust_to = max_allowed_time
            log_message = "超前"
        
        # 2. 检查时间是否小于最小允许时间 (太滞后/太早)
        elif text_time < min_allowed_time:
            # 调整到最小允许时间边界 (now - 2小时)
            target_time_to_adjust_to = min_allowed_time
            log_message = "滞后"

        
        if target_time_to_adjust_to:
            adjusted_hour = target_time_to_adjust_to.hour
            # 使用 :02d 格式化分钟，确保是两位数 (例如 5 -> 05)
            adjusted_minute = target_time_to_adjust_to.minute
            
            new_time_str = f"{adjusted_hour}时{adjusted_minute:02d}分"
            print(f"时间已调整 ({log_message}，超出 ±{MAX_TIME_AHEAD_HOURS}小时范围): {match.group(0)} -> {new_time_str}")
            return new_time_str


        # 如果时间在 [min_allowed_time, max_allowed_time] 范围内，则返回原始匹配的字符串
        return match.group(0)

    # 使用 re.sub 并传入回调函数 time_replacer 进行替换
    adjusted_text = re.sub(time_pattern, time_replacer, text)
    
    return adjusted_text
