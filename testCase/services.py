import openpyxl
import requests
import json
import tempfile
import subprocess
import os
import re
from collections import defaultdict
from django.conf import settings
from openpyxl import Workbook
from tempfile import NamedTemporaryFile
from groq import Groq

client = Groq(api_key=settings.LAMA_API_KEY)

def run_generated_test_script(script_code: str):
    """Safely run generated Selenium or Python test scripts and return output."""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as temp_file:
            temp_file.write(script_code.encode('utf-8'))
            temp_path = temp_file.name

        # Run with timeout and capture output/errors
        result = subprocess.run(
            ["python", temp_path],
            capture_output=True,
            text=True,
            timeout=20  # 20 seconds max
        )

        os.remove(temp_path)
        return {
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"error": "Test execution timed out after 20 seconds."}
    except Exception as e:
        return {"error": f"Error running generated test script: {e}"}

def generate_testcase_excel(testcases):
    """
    Generates an Excel file from AI-generated test cases.
    Returns file path.
    """

    wb = Workbook()
    ws = wb.active
    ws.title = "TestCases"

    # Header row (matches parse_testcase_excel)
    ws.append([
        "Title",
        "Preconditions",
        "Priority",
        "Severity",
        "Labels",
        "Expected Result",
        "Step Order",
        "Action",
        "Data",
        "Expected"
    ])

    for tc in testcases:
        title = tc.get("title")
        pre = tc.get("preconditions", "")
        priority = tc.get("priority", "MEDIUM")
        severity = tc.get("severity", "MINOR")
        labels = tc.get("labels", "FUNCTIONAL")
        exp_result = tc.get("expected_result", "")

        steps = tc.get("steps", [])
        if not steps:
            steps = [{
                "order": 1,
                "action": "",
                "data": "",
                "expected": ""
            }]

        for step in steps:
            ws.append([
                title,
                pre,
                priority,
                severity,
                labels,
                exp_result,
                step.get("order"),
                step.get("action"),
                step.get("data"),
                step.get("expected"),
            ])

    tmp = NamedTemporaryFile(delete=False, suffix=".xlsx")
    wb.save(tmp.name)
    tmp.close()

    return tmp.name


def get_ai_response(user_prompt: str, file_content: str = ""):
    system_prompt = """
    You are an expert QA engineer.
    Generate structured, machine-readable testcases.
    Return ONLY valid XML or JSON as requested.
    No markdown. No explanation.
    """

    full_prompt = system_prompt + "\n\n" + user_prompt

    if file_content:
        full_prompt += f"\n\nInput file:\n{file_content}"

    try:
        # Groq API Call
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": full_prompt},
            ],
            model="llama-3.3-70b-versatile", # High performance free model
            temperature=0.2, # Lower temperature for more consistent JSON
        )

        return {
            "ai_message": chat_completion.choices[0].message.content
        }

    except Exception as e:
        return {"error": f"Groq API Error: {str(e)}"}


def parse_testcase_excel(file):
    wb = openpyxl.load_workbook(file)
    ws = wb["TestCases"]

    grouped = defaultdict(lambda: {"steps": []})

    for row in ws.iter_rows(min_row=2, values_only=True):
        (
            title, pre, priority, severity, labels, exp_result,
            order, action, data, expected
        ) = row

        grouped[title]["meta"] = {
            "title": title,
            "preconditions": pre,
            "priority": priority,
            "severity": severity,
            "labels": labels,
            "expected_result": exp_result,
        }

        grouped[title]["steps"].append({
            "order": order,
            "action": action or "",
            "data": data or "",
            "expected": expected or "",
        })

    return grouped

def extract_json_from_ai(text: str):
    """
    Extracts valid JSON array/object from AI response.
    Supports markdown, prose, and fenced blocks.
    """
    # Try direct JSON first
    try:
        return json.loads(text)
    except Exception:
        pass

    # Extract fenced ```json blocks
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Extract first JSON array
    match = re.search(r"(\[\s*{.*?}\s*\])", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    # Extract first JSON object
    match = re.search(r"(\{\s*\".*?\"\s*\})", text, re.DOTALL)
    if match:
        return json.loads(match.group(1))

    raise ValueError("No valid JSON found in AI response")