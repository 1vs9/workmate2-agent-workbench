export interface CategoryFilterTabsProps {
  categories: string[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
}

export default function CategoryFilterTabs({
  categories,
  value,
  onChange,
  className = "",
}: CategoryFilterTabsProps) {
  if (categories.length <= 1) return null;

  return (
    <div className={`wm-category-tabs scrollbar-hide ${className}`.trim()} role="tablist">
      {categories.map((item) => {
        const active = value === item;
        return (
          <button
            key={item}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item)}
            className={`wm-category-tabs__item${active ? " wm-category-tabs__item--active" : ""}`}
          >
            {item}
          </button>
        );
      })}
    </div>
  );
}
