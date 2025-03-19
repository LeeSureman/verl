from math_verify import verify, parse
import torch
import re
import signal
from typing import Optional

def find_last_boxed(text):
    # 找到最后一个 \boxed{ 的位置
    start = text.rfind('\\boxed{')
    if start == -1:  # 如果没找到
        return None

    # 从 \boxed{ 开始位置往后找对应的右括号
    count = 1  # 括号计数
    pos = start + 7  # 跳过 \boxed{ 这7个字符

    while pos < len(text) and count > 0:
        if text[pos] == '{':
            count += 1
        elif text[pos] == '}':
            count -= 1
        pos += 1

    # 如果括号没有配对完
    if count > 0:
        return None

    # 返回括号内的内容
    return text[start + 7:pos - 1]

def verify_single_example(response, label):
    parsed_label = parse('$' + label + '$')

    pred_in_box = find_last_boxed(response)
    if pred_in_box == None:
        parsed_pred = []
    else:
        parsed_pred = parse('$' + pred_in_box + '$')

    result = verify(parsed_label, parsed_pred)
    return result, pred_in_box

def compute_score(solution_str: str,
                  ground_truth: str,
                  pause_tokens_index: Optional[list[int]] = None) -> float:
    correct, pred_in_box = verify_single_example(solution_str, ground_truth)
    reward = 1.0 if correct else -1.0
    acc = correct
    return {
        "score": reward,
        "acc": acc,
        "pred": pred_in_box,
    }