---
paths:
  - "services/**/*.py"
  - "services/**/test_*.py"
  - "services/**/*_test.py"
---

# 实现后必须验证

## 触发条件

完成代码实现时。

## 规则

实现功能或修复 Bug 后，必须运行测试验证，不得产出未验证的代码。

## 验证方式

1. **单元测试**：运行 pytest 测试相关模块
2. **集成测试**：启动服务验证接口可用性
3. **手动测试**：对于 UI 或复杂交互，手动验证核心路径

## 示例

```bash
# 修改代码后
Edit services/live-monitor/utils/TiktokTool.py

# 运行测试验证
cd services/live-monitor && pytest tests/test_tiktok_tool.py -v

# 或启动服务手动验证
cd services/live-monitor && python main.py
curl http://localhost:8080/liveRoom/portInfo -X POST -d '{"mateUrl":"..."}'
```

## 不合格的交付

- 测试失败但标记任务完成
- 实现部分功能就声称完成
- 遇到错误未解决就提交代码
- 找不到文件或依赖但仍继续

## 原因

未验证的代码可能引入 Bug，破坏现有功能，增加后续维护成本。验证是质量保证的最后一道防线。
