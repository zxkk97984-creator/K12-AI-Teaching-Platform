/** Student animation page (T21).
 *
 * The catalogue comes from the server-side filtered API, so unpublished,
 * withdrawn, cross-stage or wrong-revision animations never reach the browser.
 * Parameters are validated by the server before the pure step generator runs;
 * a rejected parameter set shows a readable message and no animation.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { ApiError } from "../identity/api";
import { navigate } from "../identity/session";
import { AnimationPlayer } from "./AnimationPlayer";
import { AnimationInputError, stepsForSpec } from "./templates";
import { listAnimations, requestAnimationSpec } from "./api";
import type { AnimationDefinition, AnimationSpec } from "./types";
import "./animation.css";

function textOf(caught: unknown, fallback: string): string {
  if (caught instanceof AnimationInputError) {
    return caught.message;
  }
  if (caught instanceof ApiError) {
    return caught.message.replace(/^[A-Z_]+:\s*/, "") || fallback;
  }
  return fallback;
}

function defaultParams(definition: AnimationDefinition): Record<string, unknown> {
  const source: Record<string, unknown> = definition.defaults ?? {};
  const result: Record<string, unknown> = {};
  for (const key of Object.keys(definition.param_schema.properties)) {
    result[key] = source[key];
  }
  return result;
}

function valuesText(value: unknown): string {
  return Array.isArray(value) ? value.join(",") : String(value ?? "");
}

export function AnimationPage() {
  const [definitions, setDefinitions] = useState<AnimationDefinition[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [spec, setSpec] = useState<AnimationSpec | null>(null);
  const [errorInput, setErrorInput] = useState("");
  const [targetText, setTargetText] = useState("");

  const load = useCallback(async () => {
    setError(null);
    setSpec(null);
    try {
      const payload = await listAnimations();
      setDefinitions(payload.items);
      setSelectedId(payload.items[0]?.id ?? null);
      if (payload.items.length === 0) {
        setError(null);
      }
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        navigate("/login");
        return;
      }
      setDefinitions(null);
      setError(textOf(caught, "动画列表加载失败，请稍后重试。"));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const selected = useMemo(
    () => definitions?.find((item) => item.id === selectedId) ?? null,
    [definitions, selectedId],
  );

  useEffect(() => {
    if (!selected) return;
    const params = defaultParams(selected);
    setErrorInput(valuesText(params.values));
    setTargetText(params.target === undefined ? "" : String(params.target));
  }, [selected]);

  const requestSteps = useCallback(async () => {
    if (!selected) return;
    setError(null);
    setSpec(null);
    const values = errorInput
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item.length > 0)
      .map((item) => Number(item));
    const params: Record<string, unknown> = { values };
    if ("target" in selected.param_schema.properties) {
      params.target = Number(targetText.trim());
    }
    try {
      setSpec(await requestAnimationSpec(selected.id, params));
    } catch (caught) {
      setError(textOf(caught, "参数被拒绝，请检查后重试。"));
    }
  }, [selected, errorInput, targetText]);

  const steps = useMemo(() => {
    if (!spec) return null;
    try {
      return stepsForSpec(spec);
    } catch (caught) {
      setError(textOf(caught, "参数被拒绝，请检查后重试。"));
      return null;
    }
  }, [spec]);

  return (
    <main className="animation-page" data-testid="animation-page">
      <header className="animation-header">
        <h1>教学动画</h1>
        <p>
          动画只有两种固定模板（排序、二分查找），步骤由确定性函数生成；动画外始终提供文字讲解。
        </p>
      </header>

      {error ? (
        <p className="animation-error" role="alert" data-testid="animation-error">
          {error}
        </p>
      ) : null}

      {definitions && definitions.length === 0 ? (
        <p data-testid="animation-empty-state">
          你所在学段目前没有已发布的动画。老师发布后会出现在这里。
        </p>
      ) : null}

      {definitions && definitions.length > 0 ? (
        <section className="animation-picker" data-testid="animation-picker">
          <label>
            选择动画
            <select
              value={selectedId ?? ""}
              onChange={(event) => {
                setSelectedId(event.target.value);
                setSpec(null);
              }}
              data-testid="animation-select"
            >
              {definitions.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </select>
          </label>
          {selected ? (
            <p className="animation-summary" data-testid="animation-summary">
              {selected.summary}
            </p>
          ) : null}
          {selected?.content_notice ? (
            <p className="animation-notice" data-testid="animation-notice">
              {selected.content_notice}
            </p>
          ) : null}
          {selected && selected.preconditions.length > 0 ? (
            <p className="animation-precondition" data-testid="animation-precondition">
              前提：{selected.preconditions.join("；")}
            </p>
          ) : null}

          <div className="animation-params">
            <label>
              数组（逗号分隔，1~{selected?.limits.max_items ?? 12} 个整数）
              <input
                value={errorInput}
                onChange={(event) => setErrorInput(event.target.value)}
                data-testid="animation-values"
              />
            </label>
            {selected && "target" in selected.param_schema.properties ? (
              <label>
                目标值
                <input
                  value={targetText}
                  onChange={(event) => setTargetText(event.target.value)}
                  data-testid="animation-target"
                />
              </label>
            ) : null}
            <button type="button" onClick={() => void requestSteps()} data-testid="animation-generate">
              生成步骤
            </button>
          </div>
        </section>
      ) : null}

      {steps && selected ? (
        <AnimationPlayer
          steps={steps}
          title={selected.title}
          textAlternative={selected.text_alternative}
        />
      ) : null}
    </main>
  );
}
