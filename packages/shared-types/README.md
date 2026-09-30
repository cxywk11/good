# Shared types

FastAPI/Pydantic 是 API schema 来源：运行后 `/openapi.json`。
TypeScript 调用类型维护于 `apps/web/src/api.ts`。契约扩展需同步 TypeScript 并执行 tsc。
后续可以从 OpenAPI 自动生成客户端，当前不重复维护第三份 schema。
