"""OpenClaw Skills Manager — Unified Entry Point for OpenCLaw/Bionic Skills."""

import os
import sys
import json


def normalize_trigger(trigger: str) -> str:
    """Normalize a trigger string to lowercase for comparison."""
    return trigger.strip().lower() if trigger else ""


def find_skills_in_dir(skill_dir: str, target_name: None = None) -> list:
    """Scan a directory for openclaw.json files and extract skill definitions.

    Args:
        skill_dir: Directory to scan (e.g., "E:/SKILLS")
        target_name: If set, only return skills whose name or triggers match this string.

    Returns:
        List of skill dictionaries matching the criteria.
    """
    if not os.path.isdir(skill_dir):
        print("[错误] 目录不存在：{}".format(skill_dir))
        sys.exit(1)

    skills = []
    for root, _, files in os.walk(skill_dir):
        json_file = os.path.join(root, "openclaw.json")
        if not os.path.exists(json_file):
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            skills.append(data)
        except (json.JSONDecodeError, OSError) as e:
            print("[警告] 无法读取 {}: {}".format(json_file, e))

    # Filter by target_name if specified
    if target_name is not None:
        filtered = []
        for skill in skills:
            name_norm = normalize_trigger(skill["name"])
            triggers_norms = [normalize_trigger(t) for t in skill.get("triggers", [])]
            if target_name_norm := normalize_trigger(target_name):
                if target_name_norm == name_norm or any(
                    target_name_norm in tn for tn in triggers_norms
                ):
                    filtered.append(skill)
        return filtered

    return skills


def check_dependencies(skill_data, bin_path=None):
    """Check Python dependencies for a skill.

    Args:
        skill_data: Skill metadata dict from openclaw.json
        bin_path: Path to Python executable (defaults to sys.executable)

    Returns:
        Tuple of (success, missing_bins, missing_packages)
    """
    if not os.path.exists(bin_path := bin_path or sys.executable):
        print("[错误] 无法找到解释器：{}".format(bin_path))
        return False, ["python"], []

    missing_bins = []
    missing_pkgs = []

    # Check bin tools (python, nodejs)
    if "bins" in skill_data.get("requires", {}):
        for tool in skill_data["requires"]["bins"]:
            path = None
            if tool == "python":
                path = sys.executable
            elif tool in ("nodejs", "node"):
                path = os.path.join(sys.prefix, "Scripts", "node.exe")
            elif tool in ("msedge", "chrome"):
                path = None  # Browser handled internally

            if not path or not os.path.isfile(path):
                missing_bins.append(tool)

    # Check Python packages via pip list
    if "packages" in skill_data.get("requires", {}):
        pkgs = skill_data["requires"]["packages"]
        try:
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list"],
                capture_output=True, text=True, check=False, timeout=10
            )
            installed = set()
            for line in result.stdout.splitlines():
                pkg_name = line.strip().split()[0] if line.strip() else ""
                if pkg_name:
                    installed.add(pkg_name.lower())

            for pkg in pkgs:
                if pkg not in installed and pkg.lower() not in installed:
                    missing_pkgs.append(pkg)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            missing_pkgs.append("pip")

    total_missing = len(missing_bins) + len(missing_pkgs)
    return total_missing == 0, missing_bins, missing_pkgs


def run_skill(skill_data, bin_path=None):
    """Execute a single skill by dynamically importing and calling its entry point.

    Args:
        skill_data: Skill metadata dict from openclaw.json
        bin_path: Path to Python executable (defaults to sys.executable)

    Returns:
        True if successful, False otherwise.
    """
    name = skill_data["name"]
    entry_point = skill_data.get("entry_point", "main.py")

    # Try multiple search paths for the script
    base_dir = os.path.dirname(os.path.abspath(__file__)) or "."
    full_path = None

    search_paths = [
        os.path.join(base_dir, entry_point),
        os.path.join(base_dir, "skills", name.replace("-", "_").replace(".", "_"), entry_point),
        os.path.join(base_dir, "skills", "reporting-tools", entry_point),
    ]

    for sp in search_paths:
        full_path = os.path.abspath(sp)
        if os.path.exists(full_path):
            break

    if not full_path or not os.path.isfile(full_path):
        print("[错误] 无法找到脚本 '{}'".format(entry_point))
        return False

    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("skill_" + name, full_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules["skill_" + name] = module
        spec.loader.exec_module(module)

        # Look for main() or run() function
        if hasattr(module, "main"):
            result = getattr(module, "main")(args={})
            return isinstance(result, bool) and result is True
        elif hasattr(module, "run") and callable(getattr(module, "run")):
            try:
                module.run(args={"trigger": None})  # Don't pass args to avoid recursion
                return True
            except Syste
