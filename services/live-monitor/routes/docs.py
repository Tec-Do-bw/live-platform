from fastapi import APIRouter, Request, File, UploadFile, Form, Cookie, Depends, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
import os
import re
from utils.Tools import generate_api_config, chat_with_model, register_function,parse_log_to_dict,spiderLogWrite
# 动态导入requests_config，确保每次请求都获取最新配置
import importlib
from config import account_config
from starlette.middleware.sessions import SessionMiddleware
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
import hashlib
import uuid
from typing import Optional

def get_requests_config():
    config_module = importlib.import_module('config')
    importlib.reload(config_module)
    return config_module.requests_config

def get_version_history():
    config_module = importlib.import_module('config')
    importlib.reload(config_module)
    return config_module.version_history

def get_data_need_pool():
    config_module = importlib.import_module('config')
    importlib.reload(config_module)
    return config_module.data_need_pool if hasattr(config_module, 'data_need_pool') else []


from business_functions import business_functions
import json
from datetime import datetime

router = APIRouter(prefix="/docs", tags=["docs"])

# 用于HTTP Basic Authentication
security = HTTPBasic()

# 验证用户登录
async def verify_login(request: Request):
    # 检查会话中是否有登录状态
    if not request.session.get("authenticated"):
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    return True

# 处理登录请求
@router.post("/login")
async def login(request: Request):
    try:
        form_data = await request.form()
        username = form_data.get("username")
        password = form_data.get("password")
        
        # 检查用户凭据是否匹配config.py中的account_config
        if username in account_config and account_config[username] == password:
            # 设置会话状态
            request.session["authenticated"] = True
            request.session["username"] = username
            
            return JSONResponse(content={"code": 200, "message": "success", "data": None})
        else:
            return JSONResponse(
                content={"code": 401, "message": "invalid_credentials", "data": None},
                status_code=401,
            )
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Login error: {str(e)}", "data": None},
            status_code=500
        )

# 登出
@router.get("/logout")
async def logout(request: Request):
    # 清除会话
    request.session.clear()
    return JSONResponse(content={"code": 200, "message": "success", "data": None})


for func in business_functions:
    register_function(func)

@router.post("/chat")
async def chat(request: Request):
    # 验证用户是否已登录(暂时关闭)
    # if await verify_login(request) is not True:
    #     return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    data = await request.json()
    print("chat请求数据--->",data)
    user_message = data.get("message")
    
    reply = await chat_with_model(user_message)
    print("chat_reply--->",reply)
    return {"reply": reply}

@router.get("/getConfig")
async def getConfig(request: Request):
    apiConfig = generate_api_config(get_requests_config())
    # 返回成功响应
    response = {
        'code': 200,
        'message': 'success',
        'data': apiConfig
    }
    return JSONResponse(content=response)


# 离线任务配置
@router.get("/getOfflineConfig")
async def get_offline_config(request: Request):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        script_dir = os.path.join(os.path.dirname(__file__), "..", "OfflineSpider")
        config_file_path = os.path.join(script_dir, "offlineConfig.json")
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        response = {
            'code': 200,
            'message': 'success',
            'data': config_data
        }
        return JSONResponse(content=response)
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error loading offline config: {str(e)}", "data": None},
            status_code=500
        )

@router.post("/uploadOfflineTask")
async def upload_offline_task(
    request: Request,
    script_file: UploadFile = File(...),
    platform: str = Form(...),
    description: str = Form(...),
    status: int = Form(...),
    cycle_time: int = Form(...),
    start_time: int = Form(...)
):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        # Save the uploaded script file directly to the OfflineSpider directory
        script_dir = os.path.join(os.path.dirname(__file__), "..", "OfflineSpider")
        
        # Create directory if it doesn't exist
        os.makedirs(script_dir, exist_ok=True)
        
        # Get config data first to check for existing scripts
        config_file_path = os.path.join(script_dir, "offlineConfig.json")
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        # Check if script name already exists in the platform
        original_filename = script_file.filename
        final_filename = original_filename
        
        # Check if platform exists and if script exists in that platform
        script_exists = False
        if platform in config_data:
            existing_scripts = [task["script"] for task in config_data[platform]]
            if original_filename in existing_scripts:
                script_exists = True
        
        # If script already exists, add timestamp to filename
        if script_exists:
            # 获取文件扩展名
            name_parts = original_filename.rsplit('.', 1)
            if len(name_parts) > 1:
                base_name, extension = name_parts
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                final_filename = f"{base_name}_{timestamp}.{extension}"
            else:
                timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                final_filename = f"{original_filename}_{timestamp}"
        
        # Save the file with potentially modified filename
        file_path = os.path.join(script_dir, final_filename)
        contents = await script_file.read()
        with open(file_path, "wb") as f:
            f.write(contents)
        
        # Add new task to configuration
        new_task = {
            "script": final_filename,
            "status": status,
            "cycleTime": cycle_time,
            "description": description,
            "updateTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "start_time": start_time
        }
        
        # Create platform key if not exists
        if platform not in config_data:
            config_data[platform] = []
        
        config_data[platform].append(new_task)
        
        # Save updated configuration
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        
        # Add renamed flag to response if filename was changed
        response_data = {
            "task": new_task,
            "renamed": script_exists,
            "original_filename": original_filename
        }
        
        return JSONResponse(content={"code": 200, "message": "Task uploaded successfully", "data": response_data})
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error uploading task: {str(e)}", "data": None},
            status_code=500
        )


# 离线任务立即执行
@router.post("/executeOfflineTask")
async def execute_offline_task(request: Request):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        data = await request.json()
        platform = data.get("platform")
        script = data.get("script")
        
        if not platform or not script:
            return JSONResponse(
                content={"code": 400, "message": "Missing required parameters: platform or script", "data": None},
                status_code=400
            )
        
        # Get the script path
        script_path = os.path.join(os.path.dirname(__file__), "..", "OfflineSpider", script)
        print("script_path--->",script_path)
        # Check if the script exists
        if not os.path.exists(script_path):
            return JSONResponse(
                content={"code": 404, "message": f"Script not found: {script}", "data": None},
                status_code=404
            )
        log_file_path = os.path.join(os.path.dirname(__file__),  "..","OfflineSpider", "crawl_log.log")
        current_datetime = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        logContent = f"[{current_datetime}]"+"--->"+f"[{script}]"+" is start!"
        spiderLogWrite(logContent,log_file_path=log_file_path)
        # Execute the script in a separate process
        import subprocess
        process = subprocess.Popen(["python", script_path], 
                                  stdout=subprocess.PIPE, 
                                  stderr=subprocess.PIPE)
        
        # Return success message with process ID
        return JSONResponse(content={
            "code": 200, 
            "message": "Task started successfully", 
            "data": {"pid": process.pid}
        })
        
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error executing task: {str(e)}", "data": None},
            status_code=500
        )

# 离线任务状态更新
@router.post("/updateTaskStatus")
async def update_task_status(request: Request):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        data = await request.json()
        platform = data.get("platform")
        script = data.get("script")
        status = data.get("status")
        
        if platform is None or script is None or status is None:
            return JSONResponse(
                content={"code": 400, "message": "Missing required parameters", "data": None},
                status_code=400
            )
        
        # Update the configuration file
        script_dir = os.path.join(os.path.dirname(__file__), "..", "OfflineSpider")
        config_file_path = os.path.join(script_dir, "offlineConfig.json")
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        # Find and update the task
        task_found = False
        if platform in config_data:
            for task in config_data[platform]:
                if task["script"] == script:
                    task["status"] = status
                    task["updateTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task_found = True
                    break
        
        if not task_found:
            return JSONResponse(
                content={"code": 404, "message": "Task not found", "data": None},
                status_code=404
            )
        
        # Save updated configuration
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        
        return JSONResponse(content={"code": 200, "message": "Task status updated successfully", "data": None})
    
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error updating task status: {str(e)}", "data": None},
            status_code=500
        )

# 离线任务更新
@router.post("/updateTask")
async def update_task(request: Request):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        data = await request.json()
        platform = data.get("platform")
        original_script = data.get("original_script")
        new_script_name = data.get("script_name")  # 新增参数，用于接收新的脚本名称
        description = data.get("description")
        status = data.get("status")
        cycle_time = data.get("cycle_time")
        
        if not all([platform, original_script, description is not None, status is not None, cycle_time is not None]):
            return JSONResponse(
                content={"code": 400, "message": "Missing required parameters", "data": None},
                status_code=400
            )
        
        # 更新配置文件
        script_dir = os.path.join(os.path.dirname(__file__), "..", "OfflineSpider")
        config_file_path = os.path.join(script_dir, "offlineConfig.json")
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        
        # 查找并更新任务
        task_found = False
        file_renamed = False
        final_script_name = original_script
        
        # 如果提供了新的脚本名称并且与原名称不同，则需要重命名文件
        if new_script_name and new_script_name != original_script:
            # 检查新名称是否已存在（在同一平台下）
            name_conflict = False
            if platform in config_data:
                for task in config_data[platform]:
                    if task["script"] == new_script_name and task["script"] != original_script:
                        name_conflict = True
                        break
            
            if name_conflict:
                # 文件名冲突，添加时间戳
                name_parts = new_script_name.rsplit('.', 1)
                if len(name_parts) > 1:
                    base_name, extension = name_parts
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    final_script_name = f"{base_name}_{timestamp}.{extension}"
                else:
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    final_script_name = f"{new_script_name}_{timestamp}"
            else:
                # 没有冲突，使用新名称
                final_script_name = new_script_name
            
            # 执行文件重命名
            original_file_path = os.path.join(script_dir, original_script)
            new_file_path = os.path.join(script_dir, final_script_name)
            
            if os.path.exists(original_file_path):
                try:
                    os.rename(original_file_path, new_file_path)
                    file_renamed = True
                except Exception as e:
                    return JSONResponse(
                        content={"code": 500, "message": f"Error renaming file: {str(e)}", "data": None},
                        status_code=500
                    )
        
        # 更新配置
        if platform in config_data:
            for task in config_data[platform]:
                if task["script"] == original_script:
                    task["description"] = description
                    task["status"] = status
                    task["cycleTime"] = cycle_time
                    if file_renamed:
                        task["script"] = final_script_name
                    task["updateTime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    task_found = True
                    break
        
        if not task_found:
            return JSONResponse(
                content={"code": 404, "message": "Task not found", "data": None},
                status_code=404
            )
        
        # 保存更新后的配置
        with open(config_file_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)
        
        response_data = {
            "renamed": file_renamed,
            "original_name": original_script,
            "new_name": final_script_name
        }
        
        return JSONResponse(content={
            "code": 200, 
            "message": "Task updated successfully", 
            "data": response_data
        })
        
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error updating task: {str(e)}", "data": None},
            status_code=500
        )

@router.post("/updateConfig")
async def update_config(request: Request):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        data = await request.json()
        frontend_config = data.get("config")
        
        if not frontend_config:
            return JSONResponse(
                content={"code": 400, "message": "Missing config data", "data": None},
                status_code=400
            )
        
        # 获取当前配置，用于判断是新增还是编辑
        current_config = get_requests_config()
        
        # 将前端配置转换为后端存储的结构
        new_config = {}
        for platform, apis in frontend_config.items():
            new_config[platform] = {}
            for api_name, api_config in apis.items():
                # 检查是否是编辑已有接口
                is_edit_mode = platform in current_config and api_name in current_config[platform]
                
                # 如果是编辑模式，保留原有的高级配置
                if is_edit_mode:
                    # 获取原来的配置
                    original_config = current_config[platform][api_name]
                    new_config[platform][api_name] = {
                        # 保留原有高级配置
                        "mateUrl": original_config.get("mateUrl", ""),
                        "listenUrl": original_config.get("listenUrl", ""),
                        "generateRequestsUrl": original_config.get("generateRequestsUrl", ""),
                        "addOPExec": original_config.get("addOPExec", ""),
                        "parseFunc": original_config.get("parseFunc", ""),
                        "saveFunc": original_config.get("saveFunc", ""),
                        # 更新doc部分
                        "doc": {
                            "method": api_config.get("method", "GET"),
                            "description": api_config.get("description", ""),
                            "endpoint": api_config.get("endpoint", ""),
                            "defaultParams": api_config.get("defaultParams", {}),
                            "headers": api_config.get("headers", {}),
                            "responseFieldDescription": api_config.get("responseFieldDescription", {}),
                            "docsLinks": api_config.get("docsLinks", [])
                        }
                    }
                else:
                    # 新增接口，所有高级配置设为空字符串
                    new_config[platform][api_name] = {
                        "mateUrl": "",
                        "listenUrl": "",
                        "generateRequestsUrl": "",
                        "addOPExec": "",
                        "parseFunc": "",
                        "saveFunc": "",
                        "doc": {
                            "method": api_config.get("method", "GET"),
                            "description": api_config.get("description", ""),
                            "endpoint": api_config.get("endpoint", ""),
                            "defaultParams": api_config.get("defaultParams", {}),
                            "headers": api_config.get("headers", {}),
                            "responseFieldDescription": api_config.get("responseFieldDescription", {}),
                            "docsLinks": api_config.get("docsLinks", [])
                        }
                    }
        
        # 获取config.py文件路径
        config_file_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
        
        # 读取原始config.py文件
        with open(config_file_path, "r", encoding="utf-8") as f:
            config_content = f.read()
        
        # 将新的配置转换为字符串表示
        import pprint
        config_str = pprint.pformat(new_config, indent=4, width=120)
        
        # 替换requests_config变量的值
        import re
        pattern = r"requests_config\s*=\s*\{[^}]*\}"
        if re.search(pattern, config_content, re.DOTALL):
            # 如果找到requests_config变量，替换它的值
            # 需要找到完整的requests_config定义，包含所有嵌套的括号
            start_match = re.search(r"requests_config\s*=\s*\{", config_content)
            if start_match:
                start_pos = start_match.start()
                # 通过平衡括号查找结束位置
                open_braces = 1
                end_pos = start_match.end()
                
                while open_braces > 0 and end_pos < len(config_content):
                    if config_content[end_pos] == '{':
                        open_braces += 1
                    elif config_content[end_pos] == '}':
                        open_braces -= 1
                    end_pos += 1
                
                # 替换整个requests_config定义
                new_content = config_content[:start_pos] + f"requests_config = {config_str}" + config_content[end_pos:]
            else:
                # 如果找不到开始位置，尝试使用正则替换（不太可靠）
                new_content = re.sub(
                    pattern, 
                    f"requests_config = {config_str}", 
                    config_content, 
                    flags=re.DOTALL
                )
        else:
            # 如果找不到，追加到文件末尾
            new_content = config_content + f"\n\n# 请求配置\nrequests_config = {config_str}\n"
        
        # 写入更新后的配置
        with open(config_file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        
        return JSONResponse(content={"code": 200, "message": "Configuration updated successfully", "data": None})
    
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error updating configuration: {str(e)}", "data": None},
            status_code=500
        )

# 返回用户登录状态
@router.get("/user_status")
async def get_user_status(request: Request):
    # 获取会话中的登录状态
    authenticated = request.session.get("authenticated", False)
    username = request.session.get("username", "")
    
    return JSONResponse(content={
        "authenticated": authenticated,
        "username": username
    })


# 获取离线任务执行记录
@router.get("/getTaskExecutionRecords")
async def get_task_execution_records(request: Request, script: Optional[str] = None):
    # 验证用户是否已登录
    # if await verify_login(request) is not True:
    #     return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        # 读取执行记录文件
        script_dir = os.path.join(os.path.dirname(__file__), "..", "OfflineSpider")
        records_file_path = os.path.join(script_dir, "crawl_log.log")
        
        # 如果记录文件不存在，创建一个空的记录文件
        if not os.path.exists(records_file_path):
            with open(records_file_path, "w", encoding="utf-8") as f:
                f.write("{}")
            filtered_records = {}
        else:
            # 构建返回数据
            filtered_records = parse_log_to_dict(records_file_path)
        
        # 只返回该脚本的执行记录
        if script in filtered_records.keys():
            filtered_records = {script: filtered_records[script]}
        else:
            filtered_records = {script: []}

        return JSONResponse(content={
            "code": 200,
            "message": "Success",
            "data": filtered_records
        })
    
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error retrieving execution records: {str(e)}", "data": None},
            status_code=500
        )

@router.get("/getVersionHistory")
async def get_version_history_api(request: Request):
    version_history = get_version_history()
    # 返回成功响应
    response = {
        'code': 200,
        'message': 'success',
        'data': version_history
    }
    return JSONResponse(content=response)


@router.post("/addVersionHistory")
async def add_version_history(request: Request):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        # 获取请求数据
        data = await request.json()
        
        # 验证必要字段
        required_fields = ["version", "releaseDate", "updates"]
        for field in required_fields:
            if field not in data:
                return JSONResponse(
                    content={"code": 400, "message": f"Missing required field: {field}", "data": None},
                    status_code=400
                )
        
        # 获取当前版本历史
        current_history = get_version_history()
        
        # 检查版本号是否已存在
        version_exists = any(item["version"] == data["version"] for item in current_history)
        if version_exists:
            return JSONResponse(
                content={"code": 400, "message": "Version already exists", "data": None},
                status_code=400
            )
        
        # 读取config.py文件
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()
        
        # 将新版本信息添加到version_history列表中
        new_version_str = json.dumps(data, ensure_ascii=False, indent=4)
        
        # 在version_history列表的开头插入新版本
        version_history_pattern = r"version_history\s*=\s*\["
        if re.search(version_history_pattern, config_content):
            # 找到version_history列表并在开头添加新版本
            replacement = f"version_history = [\n                {new_version_str},"
            config_content = re.sub(version_history_pattern, replacement, config_content, count=1)
            
            # 保存修改后的config.py文件
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(config_content)
            
            return JSONResponse(content={"code": 200, "message": "Version added successfully", "data": None})
        else:
            return JSONResponse(
                content={"code": 500, "message": "Could not find version_history in config.py", "data": None},
                status_code=500
            )
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error adding version history: {str(e)}", "data": None},
            status_code=500
        )

@router.get("/getDataNeedPool")
async def get_data_need_pool_api(request: Request):
    try:
        # 从config.py获取data_need_pool
        need_pool = get_data_need_pool()
        
        # 返回成功响应
        response = {
            'code': 200,
            'message': 'success',
            'data': need_pool
        }
        return JSONResponse(content=response)
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error getting data need pool: {str(e)}", "data": []},
            status_code=500
        )

@router.post("/submitDataNeed")
async def submit_data_need(request: Request):
    try:
        # 获取请求数据
        data = await request.json()
        
        # 验证必要字段
        required_fields = ["title", "description", "siteLink", "contactPerson", "contactInfo", "expectedDate"]
        for field in required_fields:
            if field not in data or not data[field]:
                return JSONResponse(
                    content={"code": 400, "message": f"Missing required field: {field}", "data": None},
                    status_code=400
                )
        
        # 获取当前需求池
        need_pool = get_data_need_pool()
        
        # 创建新需求
        new_need = {
            "needId": str(uuid.uuid4()),
            "title": data["title"],
            "description": data["description"],
            "docLink": data.get("docLink", ""),
            "siteLink": data["siteLink"],
            "contactPerson": data["contactPerson"],
            "contactInfo": data["contactInfo"],
            "expectedDate": data["expectedDate"],
            "status": "待处理",
            "createTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        # 读取config.py文件
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()
        
        # 将新需求添加到需求池
        if "data_need_pool" in config_content:
            # 已存在需求池，添加新需求
            new_need_pool = [new_need] + need_pool
            need_pool_str = json.dumps(new_need_pool, ensure_ascii=False, indent=4)
            
            # 使用正则表达式查找data_need_pool变量的定义
            data_need_pool_pattern = r"data_need_pool\s*=\s*\["
            if re.search(data_need_pool_pattern, config_content):
                # 找到data_need_pool列表并替换
                replacement = f"data_need_pool = {need_pool_str}"
                
                # 找到整个data_need_pool定义
                start_match = re.search(r"data_need_pool\s*=\s*\[", config_content)
                if start_match:
                    start_pos = start_match.start()
                    # 通过平衡括号查找结束位置
                    open_braces = 1
                    end_pos = start_match.end()
                    
                    while open_braces > 0 and end_pos < len(config_content):
                        if config_content[end_pos] == '[':
                            open_braces += 1
                        elif config_content[end_pos] == ']':
                            open_braces -= 1
                        end_pos += 1
                    
                    # 替换整个data_need_pool定义
                    modified_content = config_content[:start_pos] + replacement + config_content[end_pos:]
                    
                    # 保存修改后的config.py文件
                    with open(config_path, "w", encoding="utf-8") as f:
                        f.write(modified_content)
                    
                    return JSONResponse(content={"code": 200, "message": "Data need submitted successfully", "data": None})
            
            # 如果无法用正则替换，则返回错误
            return JSONResponse(
                content={"code": 500, "message": "Could not update data_need_pool in config.py", "data": None},
                status_code=500
            )
        else:
            # 不存在需求池，创建新的需求池变量
            new_need_pool = [new_need]
            need_pool_str = json.dumps(new_need_pool, ensure_ascii=False, indent=4)
            
            # 添加到config.py文件末尾
            new_content = config_content + f"\n\n# 爬虫数据需求池\ndata_need_pool = {need_pool_str}\n"
            
            # 保存修改后的config.py文件
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            
            return JSONResponse(content={"code": 200, "message": "Data need submitted successfully", "data": None})
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error submitting data need: {str(e)}", "data": None},
            status_code=500
        )

@router.post("/updateDataNeedStatus")
async def update_data_need_status(request: Request):
    # 验证用户是否已登录
    if await verify_login(request) is not True:
        return JSONResponse(content={"code": 401, "message": "Unauthorized", "data": None}, status_code=401)
    
    try:
        # 获取请求数据
        data = await request.json()
        
        # 验证必要字段
        required_fields = ["needId", "newStatus"]
        for field in required_fields:
            if field not in data:
                return JSONResponse(
                    content={"code": 400, "message": f"Missing required field: {field}", "data": None},
                    status_code=400
                )
        
        # 获取当前需求池
        need_pool = get_data_need_pool()
        
        # 获取需求ID和新状态
        need_id = data.get("needId")
        new_status = data.get("newStatus")
        
        # 验证状态值是否合法
        valid_statuses = ["待处理", "处理中", "已完成", "已拒绝"]
        if new_status not in valid_statuses:
            return JSONResponse(
                content={"code": 400, "message": "Invalid status value", "data": None},
                status_code=400
            )
        
        # 查找需求并更新状态
        need_found = False
        for need in need_pool:
            if need.get("needId") == need_id:
                need["status"] = new_status
                need_found = True
                break
        
        if not need_found:
            return JSONResponse(
                content={"code": 404, "message": f"Need with ID {need_id} not found", "data": None},
                status_code=404
            )
        
        # 读取config.py文件
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.py")
        with open(config_path, "r", encoding="utf-8") as f:
            config_content = f.read()
        
        # 将更新后的需求池写回配置文件
        need_pool_str = json.dumps(need_pool, ensure_ascii=False, indent=4)
        
        # 使用正则表达式查找data_need_pool变量的定义
        data_need_pool_pattern = r"data_need_pool\s*=\s*\["
        if re.search(data_need_pool_pattern, config_content):
            # 找到data_need_pool列表并替换
            replacement = f"data_need_pool = {need_pool_str}"
            
            # 找到整个data_need_pool定义
            start_match = re.search(r"data_need_pool\s*=\s*\[", config_content)
            if start_match:
                start_pos = start_match.start()
                # 通过平衡括号查找结束位置
                open_braces = 1
                end_pos = start_match.end()
                
                while open_braces > 0 and end_pos < len(config_content):
                    if config_content[end_pos] == '[':
                        open_braces += 1
                    elif config_content[end_pos] == ']':
                        open_braces -= 1
                    end_pos += 1
                
                # 替换整个data_need_pool定义
                modified_content = config_content[:start_pos] + replacement + config_content[end_pos:]
                
                # 保存修改后的config.py文件
                with open(config_path, "w", encoding="utf-8") as f:
                    f.write(modified_content)
                
                return JSONResponse(content={"code": 200, "message": "Status updated successfully", "data": None})
        
        # 如果无法用正则替换，则返回错误
        return JSONResponse(
            content={"code": 500, "message": "Could not update data_need_pool in config.py", "data": None},
            status_code=500
        )
    except Exception as e:
        return JSONResponse(
            content={"code": 500, "message": f"Error updating data need status: {str(e)}", "data": None},
            status_code=500
        )
