type Props = {
  onClick: () => void;
};

export function CodeLabBackButton({ onClick }: Props) {
  return (
    <button type="button" className="secondary codelab-back-button" onClick={onClick} aria-label="返回上一页">
      <span aria-hidden="true">←</span>
      <span className="codelab-back-full" aria-hidden="true">返回上一页</span>
      <span className="codelab-back-short" aria-hidden="true">返回</span>
    </button>
  );
}
