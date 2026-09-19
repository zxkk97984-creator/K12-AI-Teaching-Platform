export type NavItem = {
  id: "learn" | "courses" | "practice" | "growth" | "settings";
  label: string;
  href: string;
  enabled: boolean;
  ownerTask?: string;
};

/** Main navigation from plans/01 §3. Unbuilt entries are shown disabled with a reason. */
export const MAIN_NAV: NavItem[] = [
  { id: "learn", label: "学习", href: "/workbench", enabled: true },
  { id: "courses", label: "课程", href: "/courses", enabled: false, ownerTask: "T08" },
  { id: "practice", label: "练习", href: "/practice", enabled: false, ownerTask: "T15" },
  { id: "growth", label: "成长", href: "/growth", enabled: false, ownerTask: "T18" },
  { id: "settings", label: "设置", href: "/settings", enabled: true },
];
