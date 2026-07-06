interface PageErrorProps {
  message: string;
}

export default function PageError({ message }: PageErrorProps) {
  return (
    <div
      className="mb-4 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-[13px] text-red-700"
      role="alert"
    >
      加载失败：{message}
    </div>
  );
}
