import { BookOpen } from "lucide-react";
export function EmptyState({ title = "尚未选择内容", description = "从左侧选择一项后，这里会显示详细内容。" }) {
  return <div className="empty-state"><div><BookOpen size={30} /><h3>{title}</h3><p>{description}</p></div></div>;
}
