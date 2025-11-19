import inspect
import logging
from functools import wraps
from typing import Callable, List, Tuple, Any

logger = logging.getLogger('huey.validation')

class ValidationError(Exception):
    """
    参数验证异常
    """
    pass

def not_none_validator(args: Tuple[Any, ...], kwargs: dict) -> bool:
    """
    检查参数中是否有None值
    
    :param args: 位置参数
    :param kwargs: 关键字参数
    :return: 验证通过返回True，否则返回False
    """
    for arg in args:
        if arg is None:
            return False
    
    for key, value in kwargs.items():
        if value is None:
            return False
    
    return True

def validate_args(validator: Callable[[Tuple[Any, ...], dict], bool] = not_none_validator):
    """
    参数验证装饰器
    
    :param validator: 验证函数，接收args和kwargs并返回bool
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not validator(args, kwargs):
                raise ValidationError("参数验证失败")
            return func(*args, **kwargs)
        return wrapper
    return decorator

def validate_task_parameters(args: Tuple[Any, ...], kwargs: dict) -> Tuple[Tuple[Any, ...], dict]:
    """
    验证并修复任务参数
    
    :param args: 位置参数
    :param kwargs: 关键字参数
    :return: 修复后的参数
    """
    # 过滤None值
    filtered_args = tuple(arg for arg in args if arg is not None)
    
    # 修复关键字参数
    fixed_kwargs = {}
    for key, value in kwargs.items():
        if value is None:
            # 尝试获取函数的默认值
            fixed_kwargs[key] = get_default_value(func=None, param_name=key)
        else:
            fixed_kwargs[key] = value
    
    return filtered_args, fixed_kwargs

def get_default_value(func: Callable, param_name: str) -> Any:
    """
    获取函数参数的默认值
    
    :param func: 函数对象
    :param param_name: 参数名称
    :return: 参数的默认值或None
    """
    if not func:
        # 默认值映射
        default_values = {
            'timeout': 3,
            'retries': 3,
            'url': '',
            'data': {},
            'headers': {},
            'params': {},
            'max_attempts': 5,
        }
        return default_values.get(param_name, None)
    
    sig = inspect.signature(func)
    if param_name not in sig.parameters:
        return None
    
    param = sig.parameters[param_name]
    if param.default is inspect.Parameter.empty:
        return None
    
    return param.default

def analyze_function_for_null_pointer(func: Callable) -> List[str]:
    """
    静态分析函数，检测可能导致空指针异常的代码路径
    
    :param func: 函数对象
    :return: 可能的空指针风险列表
    """
    import ast
    import inspect
    
    risks = []
    
    # 获取函数源代码
    try:
        source = inspect.getsource(func)
    except (TypeError, OSError):
        return risks
    
    # 解析为AST
    tree = ast.parse(source)
    func_def = tree.body[0] if isinstance(tree.body[0], ast.FunctionDef) else None
    if not func_def:
        return risks
    
    # 遍历函数体，寻找可能的空指针风险
    for node in ast.walk(func_def):
        # 检测属性访问
        if isinstance(node, ast.Attribute):
            # 检查是否访问了可能为None的对象属性
            if isinstance(node.value, ast.Name):
                risks.append(f"可能的空指针风险：访问变量 {node.value.id}.{node.attr}")
        
        # 检测索引访问
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name):
                risks.append(f"可能的空指针风险：索引访问变量 {node.value.id}")
        
        # 检测函数调用（可能传递了None参数）
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                for arg in node.args:
                    if isinstance(arg, ast.Name) and arg.id == 'None':
                        risks.append(f"可能的空指针风险：向函数 {node.func.id} 传递了None参数")
                for keyword in node.keywords:
                    if isinstance(keyword.value, ast.Name) and keyword.value.id == 'None':
                        risks.append(f"可能的空指针风险：向函数 {node.func.id} 的参数 {keyword.arg} 传递了None")
    
    return risks
