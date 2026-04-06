"""
app/services/util_syncore.py
-----------------------------
SynCore HRMS API integration utilities.

Provides functions to:
  - Encode/decode data payloads for the SynCore API
  - Fetch employee data from the HRMS system
  - Authenticate and make API requests

Configuration:
  Set SYN_CORE_CONFIG environment variable with JSON containing:
    {
      "HR_CODE": "base64_encoded_hr_code",
      "API_BASE": "",
      "DEFAULT_USER_ID": "",
      "DEFAULT_SIGNED_ARRAY": "",
      "DATE_FMT": "%m/%d/%Y"
    }
"""

import base64
import json
import logging
import os
import requests
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Configuration ─────────────────────────────────────────────────────────────

def _load_config() -> Dict:
    """Load SynCore configuration from environment."""
    config_json = os.environ.get("SYN_CORE_CONFIG", "{}")
    try:
        config = json.loads(config_json)
    except json.JSONDecodeError:
        logger.warning("SYN_CORE_CONFIG is not valid JSON, using defaults")
        config = {}
    
    # Defaults
    return {
        "HR_CODE": config.get("HR_CODE", ""),
        "API_BASE": config.get("API_BASE", ""),
        "DEFAULT_USER_ID": config.get("DEFAULT_USER_ID", ""),
        "DEFAULT_SIGNED_ARRAY": config.get(
            "DEFAULT_SIGNED_ARRAY",
            ""
        ),
        "DATE_FMT": config.get("DATE_FMT", "%m/%d/%Y"),
    }


CONFIG = _load_config()


# ── Encoding / Decoding Utilities ─────────────────────────────────────────────

def atob(b64: str) -> str:
    """JS-like atob: decode a base64 string into a binary string (latin-1)."""
    raw = base64.b64decode(b64)
    return raw.decode('latin-1')


def btoa(binary_str: str) -> str:
    """JS-like btoa: encode a binary string (latin-1) into base64."""
    if not isinstance(binary_str, str):
        raise TypeError("btoa expects a str")
    raw = binary_str.encode('latin-1')
    return base64.b64encode(raw).decode('ascii')


def encode(data: Dict) -> Dict:
    """Encode a dict to base64 JSON payload."""
    return {"data": base64.b64encode(json.dumps(data).encode()).decode()}


def decode(res: Dict) -> Dict:
    """Decode base64 JSON response."""
    data = res["res"]
    return json.loads(base64.b64decode(data).decode())


def get_code(data: Dict) -> str:
    """Generate signed array code from user data."""
    string = f'{data["user_id"]}|{data["employee_id"]}|{data["username"]}|{data["user_type"]}'
    return btoa(string)


# ── API Request Handlers ──────────────────────────────────────────────────────

def post_request(endpoint: str, payload: Dict, log: bool = False) -> Dict:
    """Generic POST request handler with base64 encoding/decoding and logging."""
    encoded_payload = encode(payload)
    try:
        resp = requests.post(
            f"{CONFIG['API_BASE']}{endpoint}",
            json=encoded_payload,
            headers={"Content-Type": "application/json"},
            timeout=30  # Increased timeout for employee sync
        )
        if resp.status_code == 200:
            data = decode(resp.json())
            if log:
                logger.info("SynCore API response: %s", data)
            return data
        else:
            logger.error(
                "SynCore API request failed: status=%s, endpoint=%s",
                resp.status_code,
                endpoint
            )
            return {"error": f"Failed with status {resp.status_code}"}
    except requests.RequestException as e:
        logger.error("SynCore API request exception: %s", str(e))
        return {"error": f"Request failed: {str(e)}"}


def build_user_payload(
    user_id: Optional[str] = None,
    signed_array: Optional[str] = None,
    extra_fields: Optional[Dict] = None
) -> Dict:
    """Build standard user payload with optional extra fields and defaults."""
    payload = {
        "hrcode": CONFIG["HR_CODE"],
        "user_id": user_id or CONFIG["DEFAULT_USER_ID"],
        "project_status": 1,
        "signed_array": signed_array or CONFIG["DEFAULT_SIGNED_ARRAY"]
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload


# ── Employee Data Fetching ────────────────────────────────────────────────────

def get_all_employees() -> List[Dict]:
    """
    Fetch all employees from the SynCore HRMS API.
    
    Returns:
        List of employee dictionaries with the following keys:
            - user_id: str
            - employee_id: str
            - name: str
            - firm_id: str
            - username: str (email)
            - gender: str
            - reporting_time: str
            - org_team_id: str
            - syn_coin: str
            - team_lead_id: str
            - designation: str
            - user_type: str
            - workinghour: str
            - monthly_worklog_hr: str
            - overrides: str
            - modifiedby: str
            - createdby: str
            - team_lead: str
            - status: str (Active/In-Active)
            - joining_date: str (MM/DD/YYYY format)
            - leaving_date: str or None
            - training_completion_date: str or None
            - modified_date: str
            - created_date: str
            - comp_off: str
            - emergency_leave: str
            - casual_leave: str
            - extended_leave: str
            - firm_name: str
            - org_name: str
            - is_org_manager: bool
            - signed_array: str (generated)
    """
    endpoint = "/user/get_users"
    payload = build_user_payload()
    
    logger.info("Fetching all employees from SynCore HRMS")
    data = post_request(endpoint, payload, log=False)
    
    if "error" in data:
        logger.error("Failed to fetch employees: %s", data["error"])
        return []
    
    employees = []
    response_data = data.get("response_data", [])
    
    for user in response_data:
        # Add signed array to each user
        user["signed_array"] = get_code(user)
        employees.append(user)
    
    logger.info("Successfully fetched %d employees from SynCore", len(employees))
    return employees


def sync_employees_to_db() -> Dict:
    """
    Fetch all employees from SynCore API and sync to local database.
    
    Returns:
        Dictionary with sync statistics:
            - total: int (total employees from API)
            - added: int (new employees added)
            - updated: int (existing employees updated)
            - errors: int (number of errors)
            - error_details: list (error messages if any)
    """
    from app.models.syncore_employee import SynCoreEmployee
    from app import db
    from datetime import datetime
    
    employees = get_all_employees()
    stats = {
        "total": len(employees),
        "added": 0,
        "updated": 0,
        "errors": 0,
        "error_details": []
    }
    
    if not employees:
        stats["error_details"].append("No employees returned from API")
        return stats
    
    for emp_data in employees:
        try:
            # Parse dates (handle None values)
            def parse_date(date_str):
                if not date_str or date_str == "None":
                    return None
                try:
                    return datetime.strptime(date_str, CONFIG["DATE_FMT"]).date()
                except (ValueError, TypeError):
                    return None
            
            # Check if employee exists by employee_id
            existing = SynCoreEmployee.query.filter_by(
                employee_id=emp_data.get("employee_id")
            ).first()
            
            # Prepare employee data
            employee_dict = {
                "user_id": emp_data.get("user_id"),
                "employee_id": emp_data.get("employee_id"),
                "name": emp_data.get("name"),
                "firm_id": emp_data.get("firm_id"),
                "email": emp_data.get("username"),
                "gender": emp_data.get("gender"),
                "reporting_time": emp_data.get("reporting_time"),
                "org_team_id": emp_data.get("org_team_id"),
                "syn_coin": emp_data.get("syn_coin"),
                "team_lead_id": emp_data.get("team_lead_id"),
                "designation": emp_data.get("designation"),
                "user_type": emp_data.get("user_type"),
                "working_hours": emp_data.get("workinghour"),
                "monthly_worklog_hours": emp_data.get("monthly_worklog_hr"),
                "overrides": emp_data.get("overrides"),
                "modified_by": emp_data.get("modifiedby"),
                "created_by": emp_data.get("createdby"),
                "team_lead_name": emp_data.get("team_lead"),
                "status": emp_data.get("status"),
                "joining_date": parse_date(emp_data.get("joining_date")),
                "leaving_date": parse_date(emp_data.get("leaving_date")),
                "training_completion_date": parse_date(emp_data.get("training_completion_date")),
                "comp_off": emp_data.get("comp_off"),
                "emergency_leave": emp_data.get("emergency_leave"),
                "casual_leave": emp_data.get("casual_leave"),
                "extended_leave": emp_data.get("extended_leave"),
                "firm_name": emp_data.get("firm_name"),
                "org_name": emp_data.get("org_name"),
                "is_org_manager": bool(emp_data.get("is_org_manager", False)),
                "signed_array": emp_data.get("signed_array"),
            }
            
            if existing:
                # Update existing employee
                for key, value in employee_dict.items():
                    setattr(existing, key, value)
                stats["updated"] += 1
            else:
                # Create new employee
                new_employee = SynCoreEmployee(**employee_dict)
                db.session.add(new_employee)
                stats["added"] += 1
            
        except Exception as e:
            stats["errors"] += 1
            error_msg = f"Error processing employee {emp_data.get('employee_id')}: {str(e)}"
            stats["error_details"].append(error_msg)
            logger.error(error_msg)
            continue
    
    try:
        db.session.commit()
        logger.info(
            "Sync complete: %d added, %d updated, %d errors",
            stats["added"],
            stats["updated"],
            stats["errors"]
        )
    except Exception as e:
        db.session.rollback()
        error_msg = f"Database commit failed: {str(e)}"
        stats["error_details"].append(error_msg)
        logger.error(error_msg)
        stats["errors"] = stats["total"]
        stats["added"] = 0
        stats["updated"] = 0
    
    return stats


def get_today_log_status(user_id: Optional[str] = None, signed_array: Optional[str] = None) -> List[Dict]:
    """
    Fetch today's attendance log details for a specific employee.
    
    Args:
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
    
    Returns:
        List of attendance log dictionaries with keys:
            - attendance_id: str
            - total_time: str (hours)
            - ip_address: str
            - log_date: str (MM/DD/YYYY format)
            - login: str (HH:MM format)
            - logout: str (HH:MM format, "00:00" if not logged out)
    """
    endpoint = "/attendance/total_logs_detail"
    payload = build_user_payload(user_id, signed_array)
    
    logger.info("Fetching today's log status for user_id=%s", user_id)
    data = post_request(endpoint, payload, log=False)
    
    if "error" in data:
        logger.error("Failed to fetch log status: %s", data["error"])
        return []
    
    response_data = data.get("response_data", [])
    logger.info("Retrieved %d log entries", len(response_data))
    
    return response_data


def get_emp_projects(user_id: Optional[str] = None, signed_array: Optional[str] = None) -> List[Dict]:
    """
    Fetch all projects assigned to a specific employee.
    
    Args:
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
    
    Returns:
        List of project dictionaries with keys:
            - project_id: str
            - project_name: str
            - project_type_id: str
            - project_status: str (Active/In-Active)
    """
    endpoint = "/project/get_emp_projects"
    payload = build_user_payload(user_id, signed_array)
    
    logger.info("Fetching projects for user_id=%s", user_id)
    data = post_request(endpoint, payload, log=False)
    
    # Ensure data is a dictionary
    if not isinstance(data, dict):
        logger.error("Invalid response format: expected dict, got %s", type(data))
        return []
    
    if "error" in data:
        logger.error("Failed to fetch projects: %s", data["error"])
        return []
    
    response_data = data.get("response_data", [])
    
    # Ensure response_data is a list
    if not isinstance(response_data, list):
        logger.error("Invalid response_data format: expected list, got %s", type(response_data))
        return []
    
    logger.info("Retrieved %d projects", len(response_data))
    
    return response_data


def get_user_mail_setting(user_id: Optional[str] = None, signed_array: Optional[str] = None) -> Dict:
    """
    Fetch email notification settings for a specific employee.
    
    Args:
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
    
    Returns:
        Dictionary with email setting keys (various settings with 'true'/'false' values)
        Example keys: daily_worklog, daily_attendlog, apply_leave_mail, 
                     approve_leave_mail, passed_leave_action_mail, etc.
    """
    endpoint = "/setting/get_user_mail_setting"
    payload = build_user_payload(user_id, signed_array)
    
    logger.info("Fetching email settings for user_id=%s", user_id)
    data = post_request(endpoint, payload, log=False)
    
    # Ensure data is a dictionary
    if not isinstance(data, dict):
        logger.error("Invalid response format: expected dict, got %s", type(data))
        return {}
    
    if "error" in data:
        logger.error("Failed to fetch email settings: %s", data["error"])
        return {}
    
    response_data = data.get("response_data", {})
    
    # Ensure response_data is a dictionary (could be a single dict or empty)
    if isinstance(response_data, list) and len(response_data) > 0:
        response_data = response_data[0]
    elif not isinstance(response_data, dict):
        logger.error("Invalid response_data format: expected dict, got %s", type(response_data))
        return {}
    
    logger.info("Retrieved email settings with %d keys", len(response_data))
    
    return response_data


def get_attendance(
    start_date: str = "",
    end_date: str = "",
    user_id: Optional[str] = None,
    signed_array: Optional[str] = None
) -> List[Dict]:
    """
    Fetch attendance records for a specific employee within a date range.

    Args:
        start_date: Start date in MM/DD/YYYY format
        end_date: End date in MM/DD/YYYY format
        user_id: Employee user ID
        signed_array: Employee signed array for authentication

    Returns:
        List of attendance record dictionaries with keys:
            - name: str
            - user_id: str
            - attendance_id: str
            - log_date: str (MM/DD/YYYY)
            - user_override_comment: str or None
            - out_office_log: str or None
            - is_came_late: str ('-' or 'yes')
            - logged_hours: str (H:MM format)
    """
    endpoint = "/attendance/show_attendance"
    extra_fields = {"start_date": start_date, "end_date": end_date}
    payload = build_user_payload(user_id, signed_array, extra_fields)

    logger.info(
        "Fetching attendance for user_id=%s from %s to %s",
        user_id, start_date, end_date
    )
    data = post_request(endpoint, payload, log=False)

    if not isinstance(data, dict):
        logger.error("Invalid response format: expected dict, got %s", type(data))
        return []

    if "error" in data:
        logger.error("Failed to fetch attendance: %s", data["error"])
        return []

    response_data = data.get("response_data", [])
    print(response_data)
    if not isinstance(response_data, list):
        logger.error("Invalid response_data format: expected list, got %s", type(response_data))
        return []

    logger.info("Retrieved %d attendance records", len(response_data))
    return response_data


def get_project_modules(
    user_id: Optional[str] = None,
    signed_array: Optional[str] = None,
    project_id: Optional[str] = None
) -> List[Dict]:
    """
    Fetch all modules for a specific project.

    Args:
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
        project_id: Project ID to fetch modules for

    Returns:
        List of module dictionaries with keys:
            - project_id: str
            - module_id: str
            - module_name: str
            - estimated_time: str
            - module_startdate: str (MM/DD/YYYY)
            - module_enddate: str or None
            - module_status: str (e.g. 'Open')
    """
    endpoint = "/project/get_modules"
    extra_fields = {"project_id": project_id}
    payload = build_user_payload(user_id, signed_array, extra_fields)

    logger.info("Fetching modules for project_id=%s", project_id)
    data = post_request(endpoint, payload, log=False)

    if not isinstance(data, dict):
        logger.error("Invalid response format: expected dict, got %s", type(data))
        return []

    if "error" in data:
        logger.error("Failed to fetch project modules: %s", data["error"])
        return []

    response_data = data.get("response_data", [])
    if not isinstance(response_data, list):
        response_data = [response_data] if response_data else []

    logger.info("Retrieved %d modules", len(response_data))
    return response_data


def get_project_activities(
    user_id: Optional[str] = None,
    signed_array: Optional[str] = None,
    project_id: Optional[str] = None
) -> List[Dict]:
    """
    Fetch all activities for a specific project.

    Args:
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
        project_id: Project ID to fetch activities for

    Returns:
        List of activity dictionaries with keys:
            - project_id: str
            - activity_id: str
            - activity_name: str
            - total_forecast_hours: str
            - project_activity_id: str
            - act_status: str ('1' = active)
    """
    endpoint = "/project/get_activities"
    extra_fields = {"project_id": project_id}
    payload = build_user_payload(user_id, signed_array, extra_fields)

    logger.info("Fetching activities for project_id=%s", project_id)
    data = post_request(endpoint, payload, log=False)

    if not isinstance(data, dict):
        logger.error("Invalid response format: expected dict, got %s", type(data))
        return []

    if "error" in data:
        logger.error("Failed to fetch project activities: %s", data["error"])
        return []

    response_data = data.get("response_data", [])
    if not isinstance(response_data, list):
        response_data = [response_data] if response_data else []

    logger.info("Retrieved %d activities", len(response_data))
    return response_data


def get_emp_project_log(
    start_date: str = "",
    end_date: str = "",
    user_id: Optional[str] = None,
    signed_array: Optional[str] = None,
    project_id: int = 0,
    module_id: int = 0,
    activity_id: int = 0,
) -> List[Dict]:
    """
    Fetch work log entries for an employee, optionally filtered by project/module/activity.

    Args:
        start_date: Start date in MM/DD/YYYY format
        end_date: End date in MM/DD/YYYY format
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
        project_id: Filter by project (0 = all projects)
        module_id: Filter by module (0 = all modules)
        activity_id: Filter by activity (0 = all activities)

    Returns:
        List of log dictionaries with keys:
            - id: str
            - user_id: str
            - project_id: str
            - project_name: str
            - user_name: str
            - module_id: str
            - module_name: str
            - activity_id: str
            - activity_name: str
            - work_desc: str
            - log_date: str (MM/DD/YYYY)
            - hour_clocked: str
    """
    endpoint = "/project/get_emp_project_log"
    payload = {
        "hrcode": CONFIG["HR_CODE"],
        "project_id": project_id,
        "emp_id": user_id or CONFIG["DEFAULT_USER_ID"],
        "module_id": module_id,
        "activity_id": activity_id,
        "start_date": start_date,
        "end_date": end_date,
        "groupby": "none",
        "sortby": "ASC",
        "signed_array": signed_array or CONFIG["DEFAULT_SIGNED_ARRAY"],
    }

    logger.info(
        "Fetching project logs for user_id=%s project_id=%s %s to %s",
        user_id, project_id, start_date, end_date
    )
    encoded_payload = encode(payload)
    try:
        resp = requests.post(
            f"{CONFIG['API_BASE']}{endpoint}",
            json=encoded_payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = decode(resp.json())
        else:
            logger.error("Project log request failed: status=%s", resp.status_code)
            return []
    except Exception as e:
        logger.error("Project log request exception: %s", str(e))
        return []

    response_data = data.get("response_data", [])
    if not isinstance(response_data, list):
        response_data = [response_data] if response_data else []

    logger.info("Retrieved %d log entries", len(response_data))
    return response_data


def login(user_id: Optional[str] = None, signed_array: Optional[str] = None, override_comment: str = "") -> Dict:
    """
    Mark employee login/attendance entry.
    
    Args:
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
        override_comment: Optional comment for the attendance override
    
    Returns:
        Dictionary with:
            - message: str (success/error message)
            - any additional response data
    """
    endpoint = "/attendance/fill_attendance"
    extra_fields = {"override_comment": override_comment}
    payload = build_user_payload(user_id, signed_array, extra_fields)
    
    logger.info("Marking login for user_id=%s with comment=%s", user_id, override_comment[:50] if override_comment else "None")
    data = post_request(endpoint, payload, log=False)
    
    # Ensure data is a dictionary
    if not isinstance(data, dict):
        logger.error("Invalid response format: expected dict, got %s", type(data))
        return {"error": "Invalid response format"}
    
    # If there's an error from the API call, return it
    if "error" in data:
        return data
    
    # Otherwise return the response with message
    result = data.get("response_data", {})
    result["message"] = data.get("message", "")
    
    return result


def logout(user_id: Optional[str] = None, signed_array: Optional[str] = None, override_comment: str = "") -> Dict:
    """
    Mark employee logout/attendance exit.
    
    Args:
        user_id: Employee user ID
        signed_array: Employee signed array for authentication
        override_comment: Optional comment for the attendance override
    
    Returns:
        Dictionary with:
            - message: str (success/error message)
            - any additional response data
    """
    endpoint = "/attendance/fill_attendance"
    extra_fields = {"override_comment": override_comment}
    payload = build_user_payload(user_id, signed_array, extra_fields)
    
    logger.info("Marking logout for user_id=%s with comment=%s", user_id, override_comment[:50] if override_comment else "None")
    data = post_request(endpoint, payload, log=False)
    
    # Ensure data is a dictionary
    if not isinstance(data, dict):
        logger.error("Invalid response format: expected dict, got %s", type(data))
        return {"error": "Invalid response format"}
    
    # If there's an error from the API call, return it
    if "error" in data:
        return data
    
    # Otherwise return the response with message
    result = data.get("response_data", {})
    result["message"] = data.get("message", "")
    
    return result


def fill_work_log(
    project_id,
    module_id,
    activity_id,
    work_desc: str,
    hour_clocked,
    user_id: Optional[str] = None,
    signed_array: Optional[str] = None,
) -> Dict:
    """
    Submit a daily work log entry for an employee.

    Args:
        project_id:    Project ID for this log entry
        module_id:     Module ID within the project
        activity_id:   Activity ID within the project
        work_desc:     Work description / summary
        hour_clocked:  Hours worked (numeric or string)
        user_id:       Employee user ID
        signed_array:  Employee signed array for authentication

    Returns:
        Dict with either:
            {"token": <response_data>, "message": ...}  on success
            {"error": <message>}                        on failure
    """
    endpoint = "/project/fill_daily_log"

    extra_fields = {
        "project_id1":       project_id,
        "module_id1":        module_id,
        "activity_id1":      activity_id,
        "work_desc1":        work_desc,
        "hour_clocked1":     hour_clocked,
        "work_quantified11": "",
        "work_quantified21": "",
        "log_date1":         "",
        "send_mail1":        "false",
        "project_id2":       0,
        "module_id2":        0,
        "activity_id2":      0,
        "work_quantified12": "",
        "work_quantified22": "",
        "log_date2":         "",
        "send_mail2":        "false",
    }
    payload = build_user_payload(user_id, signed_array, extra_fields)

    logger.info(
        "Filling work log for user_id=%s project_id=%s module_id=%s activity_id=%s hours=%s",
        user_id, project_id, module_id, activity_id, hour_clocked,
    )
    data = post_request(endpoint, payload, log=False)

    if not isinstance(data, dict):
        return {"error": "Invalid response format"}

    if "error" in data:
        return {"error": data["error"]}

    if data.get("status") == "Success":
        return {
            "token":   data.get("response_data", data),
            "message": data.get("message", "Work log submitted successfully."),
        }

    return {"error": data.get("message", "Failed to submit work log.")}
