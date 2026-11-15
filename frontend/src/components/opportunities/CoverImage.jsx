import { useState } from "react";
import { BookOpen, Briefcase, GraduationCap, Rocket } from "lucide-react";
import { cx } from "../ui";

/*
  Listing images are hot-linked from the organiser's site and are often
  missing or blocked. Then a designed placeholder takes their place: a tint
  and icon per role type, with the organisation's initial.
*/
const LOOKS = {
  internship: { icon: Rocket, tint: "from-brand-soft to-surface-2" },
  graduate_programme: { icon: GraduationCap, tint: "from-accent-soft to-surface-2" },
  entry_level: { icon: Briefcase, tint: "from-brand-soft to-accent-soft" },
  graduate_school: { icon: BookOpen, tint: "from-surface-2 to-brand-soft" },
};

export default function CoverImage({ src, roleType, organisation, className }) {
  const [failed, setFailed] = useState(false);
  const look = LOOKS[roleType] || LOOKS.entry_level;
  const Icon = look.icon;

  if (src && !failed) {
    return (
      <img
        src={src}
        alt=""
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        className={cx("bg-surface-2 object-cover", className)}
      />
    );
  }
  const initial = (organisation || "").trim().charAt(0).toUpperCase();
  return (
    <div aria-hidden className={cx("relative flex items-center justify-center overflow-hidden bg-gradient-to-br", look.tint, className)}>
      <Icon className="size-10 text-brand/70" strokeWidth={1.5} />
      {initial && (
        <span className="absolute right-3 bottom-2 text-4xl font-bold text-brand/10 select-none">{initial}</span>
      )}
    </div>
  );
}
