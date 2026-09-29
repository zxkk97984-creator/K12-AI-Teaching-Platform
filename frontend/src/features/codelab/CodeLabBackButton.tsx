type Props = {
  onClick: () => void;
};

export function CodeLabBackButton({ onClick }: Props) {
  return (
    <button type="button" className="secondary codelab-back-button" onClick={onClick}>
      <span aria-hidden="true">←</span>
      返回上一页
    </button>
  );
}
