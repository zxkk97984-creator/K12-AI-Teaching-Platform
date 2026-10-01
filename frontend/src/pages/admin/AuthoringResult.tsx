import ReactMarkdown from "react-markdown";
const list = (value: unknown) => (Array.isArray(value) ? value : []);
export function AuthoringResult({ spec }: { spec: Record<string, unknown> }) {
  const objectives = list(spec.objectives).filter(
    (value): value is string => typeof value === "string",
  );
  const script =
    typeof spec.teaching_script === "string" ? spec.teaching_script : "";
  const activities = list(spec.activities).filter(
    (value): value is Record<string, unknown> =>
      Boolean(value) && typeof value === "object",
  );
  const warnings = list(spec.warnings).filter(
    (value): value is string => typeof value === "string",
  );
  return (
    <div className="admin-generated-content">
      {objectives.length > 0 && (
        <>
          <h4>教学目标</h4>
          <ul>
            {objectives.map((value, index) => (
              <li key={index}>{value}</li>
            ))}
          </ul>
        </>
      )}
      {script && (
        <>
          <h4>讲解脚本</h4>
          <div className="admin-generated-markdown">
            <ReactMarkdown skipHtml>{script}</ReactMarkdown>
          </div>
        </>
      )}
      {activities.length > 0 && (
        <>
          <h4>教学活动</h4>
          <ol>
            {activities.map((value, index) => (
              <li key={index}>
                <strong>
                  {(
                    {
                      ANIMATION: "动画观察",
                      RESOURCE: "资料阅读",
                      DISCUSSION: "讨论",
                      PRACTICE: "练习",
                      QUIZ: "问答",
                      INTERACTIVE: "互动活动",
                    } as Record<string, string>
                  )[String(value.kind)] ?? "教学活动"}
                </strong>
                <p>{String(value.instruction ?? "")}</p>
                {value.suggested_resource_id ? (
                  <small className="admin-muted">
                    建议资源：{String(value.suggested_resource_id)}
                  </small>
                ) : null}
              </li>
            ))}
          </ol>
        </>
      )}
      {warnings.map((warning, index) => (
        <p className="admin-warning" key={index}>
          {warning}
        </p>
      ))}
      <details className="admin-technical">
        <summary>完整生成规格（含动画与来源引用）</summary>
        <pre className="admin-package-spec">
          {JSON.stringify(spec, null, 2)}
        </pre>
      </details>
      <p className="admin-help">
        内容来自服务器生成记录。当前接口不提供产物下载，文件审校仍需核查实际存储产物。
      </p>
    </div>
  );
}
