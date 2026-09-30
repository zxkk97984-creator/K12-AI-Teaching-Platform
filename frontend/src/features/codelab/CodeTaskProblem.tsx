import { Link } from "react-router-dom";
import type { CodeTask } from "./types";

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function schemaText(value: unknown): string {
  const schema = object(value);
  const types: Record<string, string> = { integer: "整数", number: "数值", string: "字符串", boolean: "布尔值", array: "列表", object: "对象", null: "空值" };
  const parts = [types[String(schema.type)] ?? String(schema.type ?? "见完整规则")];
  if (schema.items) parts.push(`元素：${schemaText(schema.items)}`);
  if (schema.properties) {
    const required = Array.isArray(schema.required) ? schema.required : [];
    parts.push(`字段：${Object.entries(object(schema.properties)).map(([name, field]) => `${name}${required.includes(name) ? "（必需）" : ""}：${schemaText(field)}`).join("；")}`);
  }
  if (schema.anyOf || schema.oneOf) {
    const alternatives = schema.anyOf ?? schema.oneOf;
    if (Array.isArray(alternatives)) parts.push(`可返回 ${alternatives.map(schemaText).join(" 或 ")}`);
  }
  if (schema.const !== undefined) parts.push(`固定值 ${JSON.stringify(schema.const)}`);
  for (const [key, label] of Object.entries({ minimum: "最小值", maximum: "最大值", exclusiveMinimum: "大于", exclusiveMaximum: "小于", minItems: "至少元素", maxItems: "最多元素", minLength: "最短长度", maxLength: "最长长度", pattern: "匹配规则", multipleOf: "倍数" })) {
    if (schema[key] !== undefined) parts.push(`${label} ${String(schema[key])}`);
  }
  if (schema.uniqueItems === true) parts.push("元素不能重复");
  if (schema.enum) parts.push(`可选值 ${JSON.stringify(schema.enum)}`);
  if (schema.description) parts.push(String(schema.description));
  return parts.join("；");
}

function IOContract({ task }: { task: CodeTask }) {
  const input = object(task.io_contract.input_schema);
  const output = task.io_contract.output_schema;
  const properties = Object.entries(object(input.properties));
  const required = Array.isArray(input.required) ? input.required : [];
  return <section className="codelab-io-contract" aria-label="输入输出范围">
    <h2>输入与输出</h2>
    {properties.length ? <dl className="codelab-input-fields">
      {properties.map(([name, schema]) => <div key={name}><dt><code>{name}</code>{required.includes(name) ? <small>必需</small> : null}</dt><dd>{schemaText(schema)}</dd></div>)}
      {input.additionalProperties === false ? <div><dt>输入规则</dt><dd>不接受其他输入字段。</dd></div> : null}
    </dl> : <p className="codelab-muted">输入规则以题意及下方完整规则为准。</p>}
    {output ? <p className="codelab-output-rule"><strong>返回值：</strong>{schemaText(output)}</p> : null}
    {input.type || output ? <details className="codelab-schema-details">
      <summary>完整输入输出规则</summary>
      <p>输入</p><pre>{JSON.stringify(input, null, 2)}</pre>
      <p>输出</p><pre>{JSON.stringify(output, null, 2)}</pre>
    </details> : null}
  </section>;
}

export function CodeTaskProblem({ task }: { task: CodeTask }) {
  const signature = task.starter_code.match(/(?:^|\n)\s*(?:async\s+)?def\s+([A-Za-z_]\w*)\s*\([\s\S]*?\)\s*(?:->[^\n:]+)?\s*:/g)
    ?.find((header) => header.match(/def\s+([A-Za-z_]\w*)/)?.[1] === task.entrypoint)?.trim().replace(/:\s*$/, "");
  return <>
    <h2 className="codelab-problem-heading">题目说明</h2>
    <p className="codelab-problem-description">{task.description}</p>
    <section className="codelab-signature"><h2>函数签名</h2><pre>{signature ?? task.entrypoint}</pre>
      {!signature ? <details open><summary>初始代码</summary><pre>{task.starter_code}</pre></details> : null}
    </section>
    <IOContract task={task} />
    <section className="codelab-examples" aria-label="公开示例">
      <h2>公开示例</h2>
      {task.examples.map((example, index) => <details key={`${task.task_id}-${index}`} open={index === 0 ? true : undefined}>
        <summary>示例 {index + 1}</summary>
        <dl><div><dt>输入</dt><dd><pre>{JSON.stringify(example.input, null, 2)}</pre></dd></div><div><dt>预期输出</dt><dd><pre>{JSON.stringify(example.output, null, 2)}</pre></dd></div></dl>
      </details>)}
    </section>
    {task.course_link ? <section className="codelab-course-link">
      <h2>关联课程</h2><p>{task.course_link.course_title} · {task.course_link.chapter_title}</p>
      {task.course_link.available && task.course_link.href ? <Link to={task.course_link.href}>打开关联章节</Link> : <span>当前不可打开</span>}
    </section> : null}
    <details className="codelab-technical-details"><summary>技术详情</summary>
      <dl className="codelab-contract"><div><dt>题目版本</dt><dd>{task.task_id} · r{task.revision}</dd></div><div><dt>语言与协议</dt><dd>Python · {String(task.io_contract.protocol ?? "function-json.v1")}</dd></div></dl>
      {task.io_contract.limits ? <pre>{JSON.stringify(task.io_contract.limits, null, 2)}</pre> : null}
    </details>
  </>;
}
