import jsonlines
from collections import defaultdict
import json
import logging
from typing import Any, Dict, List, Optional
import copy
from typing import Optional, Callable, Dict
import ast
import copy
import faulthandler
import io
import multiprocessing
import time
import sys
from tqdm import tqdm

def prepare_test_input_output_std(test_case):
    test_input = test_case["input"]
    test_output = test_case["output"].strip()
    if test_output.endswith("-"):
        test_output = test_output[: test_output.rfind("-")].rstrip()  # Remove '-' if present and trailing
    return test_input, test_output

def run_test_std(completion, test_input, test_output):
    with io.StringIO() as output:
        sys.stdout = output
        sys.stdin = io.StringIO(test_input)
        # print(test_input,file=sys.stderr)
        try:
            final_run_code = f'__name__ = "__main__"\n{completion}' if '__name__ == "__main__"' in completion else completion
            # print()
            exec(final_run_code, {})
            return output.getvalue().strip() == test_output, output.getvalue().strip()
        finally:
            sys.stdout = sys.__stdout__


def reliability_guard(maximum_memory_bytes: Optional[int] = None):
    """
    This disables various destructive functions and prevents the generated code
    from interfering with the test (e.g. fork bomb, killing other processes,
    removing filesystem files, etc.)

    WARNING
    This function is NOT a security sandbox. Untrusted code, including, model-
    generated code, should not be blindly executed outside of one. See the
    Codex paper for more information about OpenAI's code sandbox, and proceed
    with caution.
    """

    faulthandler.disable()

    import builtins

    builtins.exit = None
    builtins.quit = None

    import os

    os.environ["OMP_NUM_THREADS"] = "1"

    os.kill = None
    os.system = None
    os.putenv = None
    os.remove = None
    os.removedirs = None
    os.rmdir = None
    os.fchdir = None
    os.setuid = None
    os.fork = None
    os.forkpty = None
    os.killpg = None
    os.rename = None
    os.renames = None
    os.truncate = None
    os.replace = None
    os.unlink = None
    os.fchmod = None
    os.fchown = None
    os.chmod = None
    os.chown = None
    os.chroot = None
    os.fchdir = None
    os.lchflags = None
    os.lchmod = None
    os.lchown = None
    os.getcwd = None
    os.chdir = None

    import shutil

    shutil.rmtree = None
    shutil.move = None
    shutil.chown = None

    import subprocess

    subprocess.Popen = None  # type: ignore

    # __builtins__["help"] = None   # this line is commented out as it results into error

    import sys

    sys.modules["ipdb"] = None
    sys.modules["joblib"] = None
    sys.modules["resource"] = None
    sys.modules["psutil"] = None
    sys.modules["tkinter"] = None

def run_tests_for_one_example(test_cases, completion, result_list, is_extracted):
    time_elapsed = float("inf")
    test_type = test_cases[0]["testtype"]
    reliability_guard()
    for i, test_case in enumerate(test_cases):
        output_error = ""
        output_value = ""
        try:
            time_start = time.time()
            if test_type == "functional":
                test_input, test_output = prepare_test_input_output_functional(test_case, is_extracted)
                passed, output_value = run_test_func(
                    completion, is_extracted, copy.deepcopy(test_input), copy.deepcopy(test_output)
                )
            else:
                test_input, test_output = prepare_test_input_output_std(test_case)
                passed, output_value = run_test_std(completion, copy.deepcopy(test_input), copy.deepcopy(test_output))
            time_elapsed = time.time() - time_start
            if not passed:
                output_error = (
                    f"For test input: {test_input}. Expected output is: {test_output}, but got: {output_value}."
                )

        except Exception as e:
            passed = False
            output_error = f"For test input: {test_input}. Expected output is: {test_output}, but got error: {e}."
            output_value = f"Error: {e}."
        if output_error == "":
            output_error = f"For test input: {test_input}. Expected output is: {test_output}, your solution correctly passes this test with output {output_value}."
        result_list.append((passed, output_error, output_value, time_elapsed))
        if not passed:
            return

def post_process_code(code):

    code = code.split("</code>")[0]
    code = code.replace("```python", "")
    code = code.split("```")[0]
    code = code.replace("<code>", "")

    return code

def prepare_test_input_output_functional(test_case, is_extracted):
    if not is_extracted:
        # Extract input and expected output from JSON directly
        test_input = test_case["input"]
        test_output = test_case["output"]
        return test_input, test_output
    else:
        # Robustly process complex inputs
        input_str = test_case["input"]
        expected_output = test_case["output"].strip()
        inputs = []

        if "=" in input_str:
            parts = input_str.split(",") if "," in input_str else [input_str]
            for part in parts:
                key, value = map(str.strip, part.split("="))
                try:
                    value = int(value)
                except ValueError:
                    try:
                        value = float(value)
                    except ValueError:
                        value = value.strip('"')
                inputs.append(value)
        else:
            for line in input_str.split("\n"):
                line = line.strip()
                if not line:
                    continue
                if line.startswith('"') and line.endswith('"'):
                    inputs.append(line.strip('"'))
                    continue
                if line.startswith("[") and line.endswith("]"):
                    inputs.append(json.loads(line))
                    continue
                try:
                    inputs.append(int(line))
                except ValueError:
                    try:
                        inputs.append(float(line))
                    except ValueError:
                        inputs.append(line)

        try:
            expected_output = json.loads(expected_output)
        except json.JSONDecodeError:
            expected_output = expected_output.strip()
        return inputs, expected_output

def run_test_func(completion, is_extracted, test_input, test_output):
    namespace = {}
    exec(completion, namespace)
    func_name = completion.split("(")[0].split()[-1]

    output = io.StringIO()
    sys.stdout = output

    try:
        if not is_extracted:
            if isinstance(test_input, dict):
                result_output = namespace[func_name](**test_input)
            else:
                result_output = namespace[func_name](test_input)
        else:
            result_output = namespace[func_name](*test_input)

        if result_output != test_output:
            return False, result_output

        return True, result_output

    except Exception as e:
        error_msg = f"Error: {str(e)}" if not is_extracted else str(e)
        return False, error_msg

    finally:
        sys.stdout = sys.__stdout__

def lcb_run(problem, completion, timeout, is_extracted):
    test_cases = problem["test"]
    manager = multiprocessing.Manager()
    result = manager.list()
    print('before entering run_tests_for_one_example')
    p = multiprocessing.Process(target=run_tests_for_one_example, args=(test_cases, completion, result, is_extracted))
    p.start()
    p.join(timeout=(timeout + 1) * len(test_cases) + 5)
    if p.is_alive():
        p.kill()

    # if len(result) < len(test_cases): failed due to timeout
    for i in range(len(test_cases) - len(result)):
        result.append((False, f"Time out!.", "Error: Time out!", float("inf")))
    # print(result)
    # print('comletion:')
    # print(completion)
    return result


def check_correctness(problem: Dict, completion: str, timeout: float, is_extracted: bool = False) -> Dict:
    """
        Evaluates the functional correctness of a completion by running the test
        suite provided in the problem.

        :param completion_id: an optional completion ID so we can match
            the results later even if execution finishes asynchronously.
    """
    result_list = lcb_run(problem, completion, timeout, is_extracted)
    details = [r[0] for r in result_list]
    all_passed = all(details)

    result = ""
    if result_list and all_passed:
        result = "passed"

    return result == "passed", list(result_list)


def extract_last_python_code(text):
    # 将所有的```PYTHON (不分大小写) 统一替换为 ```python
    text = text.replace("```PYTHON", "```python")
    text = text.replace("```Python", "```python")

    # 查找最后一个 ```python 的位置
    start_pos = text.rfind("```python")
    if start_pos == -1:
        return None  # 没找到则返回 None

    # 从该位置往后查找第一个 ``` 作为结束标记
    start_pos += 9  # 跳过 ```python
    end_pos = text.find("```", start_pos)
    if end_pos == -1:
        return None  # 没找到结束标记则返回 None

    # 提取代码内容并去除首尾空白
    code = text[start_pos:end_pos].strip()
    return code

def transform_example(js):
    example = copy.deepcopy(js['metadata'])
    example['model_answer'] = extract_last_python_code(js['generation_output']['assistant_turns'][0]['message'])
    # print('extracted code:')
    # print(example['model_answer'])
    # example['difficulty'] = js['difficulty']
    return example

def evaluate_single_example(example):
    """Helper function to evaluate a single example"""
    try:
        response_entry = {
            "content": example["model_answer"],
            "difficulty": example["difficulty"],
            "correctness": None,
            "reason": None,
        }

        code_filter_result = example["model_answer"]

        if not code_filter_result or len(code_filter_result) == 0:
            response_entry["correctness"] = False
            response_entry["reason"] = "Does not contain code component."
            return response_entry

        try:
                # last_code = code_filter_result[-1]
            last_code = code_filter_result
            problem_to_check = copy.deepcopy(example)

                # Add debugging
            print(f"Evaluating {example['difficulty']} problem...")

                # Add timeout handling
            curr_res, res_list = check_correctness(
                    problem=problem_to_check,
                    completion=post_process_code(last_code),
                    timeout=6,
                    is_extracted=not problem_to_check["is_stdin"],
            )

                # Log the result
            print(f"Result for {example['difficulty']}: {curr_res}")

            response_entry["correctness"] = curr_res
            response_entry["reason"] = "" if curr_res else "Code is incorrect."
            response_entry['res_list'] = res_list

        except Exception as e:
            print(f"Error evaluating {example['difficulty']} example: {str(e)}")
            response_entry["correctness"] = False
            response_entry["reason"] = f"Evaluation error: {str(e)}"

        return response_entry

    except Exception as outer_e:
        print(f"Outer error in evaluate_single_example: {str(outer_e)}")
        return {
                "content": example.get("model_answer"),
                "difficulty": example.get("difficulty"),
                "correctness": False,
                "reason": f"Critical error: {str(outer_e)}",

        }

def has_test_type(tests, type):  ## helper to select specific type of problems
    """
    Check if any test in the test list has 'testtype' set to 'type'.
    """
    # test_list = json.loads(tests)
    test_list = tests
    for test in test_list:
        if test.get("testtype") == type:
            return True
    return False

def compute_score(completion, test_cases):
    example = {}
    code = extract_last_python_code(completion)
    example["model_answer"] = code

    if isinstance(test_cases, str):
        test_cases = json.loads(test_cases)

    example['is_stdin'] = has_test_type(test_cases, "stdin")
    example['difficulty'] = 'default'
    example['test'] = test_cases

    result = evaluate_single_example(example)
    correctness = result["correctness"]
    result_dict = {
        "score": int(correctness),
        "acc": correctness,
        "pred": code,
    }
    return result_dict

