import type { ExploreAnnouncement } from "@/lib/types";

export function AnnouncementList({
  announcements,
}: {
  announcements: ExploreAnnouncement[];
}) {
  return (
    <ul className="announcement-list">
      {announcements.map((announcement) => (
        <li key={announcement.id}>
          <a
            className="text-link"
            href={announcement.url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {announcement.title}
            <span className="sr-only"> (새 창)</span>
          </a>
          <p className="muted">
            {announcement.org ?? "기관 미표기"}
            {announcement.apply_to && ` · 마감 ${announcement.apply_to}`}
          </p>
        </li>
      ))}
    </ul>
  );
}
