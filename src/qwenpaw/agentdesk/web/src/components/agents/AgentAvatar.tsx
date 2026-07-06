import { useEffect, useRef, useState, type CSSProperties } from "react";
import { avatarsApi } from "../../api/avatars";
import {
  getAvatarColorsFromName,
  isAvatarImageUrl,
} from "../../utils/agentAvatar";

export interface AgentAvatarProps {
  name: string;
  avatar?: string;
  description?: string;
  /** Seed source when generating a portrait (defaults to `name`). */
  portraitName?: string;
  /** Seed source when generating a portrait (defaults to `description`). */
  portraitDescription?: string;
  role?: "employee" | "team";
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE_CLASS = {
  sm: "wm-agent-avatar--sm",
  md: "wm-agent-avatar--md",
  lg: "wm-agent-avatar--lg",
} as const;

function portraitSeedName(name: string, portraitName?: string): string {
  return (portraitName ?? name).trim() || name;
}

function portraitSeedDescription(
  description: string,
  portraitDescription?: string,
): string {
  return portraitDescription ?? description;
}

export default function AgentAvatar({
  name,
  avatar,
  description = "",
  portraitName,
  portraitDescription,
  role = "employee",
  size = "md",
  className = "",
}: AgentAvatarProps) {
  const colors = getAvatarColorsFromName(name);
  const storedUrl = isAvatarImageUrl(avatar) ? avatar!.trim() : undefined;
  const seedName = portraitSeedName(name, portraitName);
  const seedDescription = portraitSeedDescription(description, portraitDescription);

  const [resolvedUrl, setResolvedUrl] = useState<string | undefined>(storedUrl);
  const [imageFailed, setImageFailed] = useState(false);
  const retriedRef = useRef(false);

  useEffect(() => {
    setImageFailed(false);
    retriedRef.current = false;

    if (storedUrl) {
      setResolvedUrl(storedUrl);
      return;
    }

    let cancelled = false;
    setResolvedUrl(undefined);
    void avatarsApi
      .generate({
        name: seedName,
        description: seedDescription,
        role,
      })
      .then((response) => {
        if (!cancelled) setResolvedUrl(response.url);
      })
      .catch(() => {
        if (!cancelled) setImageFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [storedUrl, seedName, seedDescription, role]);

  const handleImageError = () => {
    if (imageFailed || retriedRef.current) {
      setImageFailed(true);
      return;
    }

    retriedRef.current = true;
    void avatarsApi
      .generate({
        name: seedName,
        description: seedDescription,
        role,
      })
      .then((response) => {
        setImageFailed(false);
        setResolvedUrl(response.url);
      })
      .catch(() => {
        setImageFailed(true);
      });
  };

  const showImage = Boolean(resolvedUrl) && !imageFailed;

  return (
    <span
      className={`wm-agent-avatar ${SIZE_CLASS[size]} ${className} ${
        !showImage ? "wm-agent-avatar--empty" : ""
      }`.trim()}
      style={
        {
          "--wm-avatar-bg": colors.bg,
          "--wm-avatar-fg": colors.text,
        } as CSSProperties
      }
      aria-hidden={!showImage ? true : undefined}
    >
      {showImage ? (
        <img
          src={resolvedUrl}
          alt={name}
          className="wm-agent-avatar__img"
          onError={handleImageError}
        />
      ) : null}
    </span>
  );
}
