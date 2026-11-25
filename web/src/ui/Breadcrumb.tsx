import "./Breadcrumb.css";
import { Icon } from "./Icon";

export type Crumb = { label: string; href?: string };

// The last item without a link is the page the user is on.
export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb">
      <ol className="crumbs">
        {items.map((item, index) => {
          const isCurrent = index === items.length - 1 && item.href === undefined;
          return (
            <li key={`${index}:${item.label}`}>
              {index > 0 && <Icon name="chevron-right" />}
              {item.href !== undefined ? (
                <a href={item.href}>{item.label}</a>
              ) : (
                <span aria-current={isCurrent ? "page" : undefined}>{item.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
