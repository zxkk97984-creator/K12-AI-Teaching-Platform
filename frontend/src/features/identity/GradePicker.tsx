import { GRADE_OPTIONS, type Stage } from "./types";
import "./grade-picker.css";

const GROUPS: Array<{ label: "小学" | "初中" | "高中"; hint: string }> = [
  { label: "小学", hint: "一年级至六年级" },
  { label: "初中", hint: "初一至初三" },
  { label: "高中", hint: "高一至高三" },
];

export function GradePicker({
  value,
  onChange,
  name = "grade",
}: {
  value: number | null;
  onChange: (grade: number, stage: Stage) => void;
  name?: string;
}) {
  return <fieldset className="grade-picker">
    <legend>选择年级</legend>
    <div className="grade-picker-groups">
      {GROUPS.map((group) => <div className="grade-picker-group" key={group.label}>
        <div className="grade-picker-group-title"><strong>{group.label}</strong><small>{group.hint}</small></div>
        <div className="grade-picker-options">
          {GRADE_OPTIONS.filter((item) => item.group === group.label).map((item) => <label key={item.value} className={value === item.value ? "is-selected" : ""}>
            <input type="radio" name={name} value={item.value} checked={value === item.value} onChange={() => onChange(item.value, item.stage)} />
            <span>{item.label}</span>
          </label>)}
        </div>
      </div>)}
    </div>
  </fieldset>;
}
