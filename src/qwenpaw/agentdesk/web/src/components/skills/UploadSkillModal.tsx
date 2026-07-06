import { useCallback, useRef, useState } from "react";
import { Modal, message } from "antd";
import { ApiError } from "../../api/request";
import { skillsApi, type SkillItem, type SkillUploadResult } from "../../api/skills";
import {
  formatSkillUploadConflictMessage,
  parseSkillUploadConflictDetail,
} from "../../utils/parseSkillUploadError";

export type { SkillUploadResult };

interface UploadSkillModalProps {
  open: boolean;
  onClose: () => void;
  onUploaded?: (result: SkillUploadResult) => void;
}

type SelectedUpload = File | File[];

function uploadLabel(payload: SelectedUpload): string {
  if (Array.isArray(payload)) {
    const root = payload[0]?.webkitRelativePath?.split("/")?.[0] || "文件夹";
    return `${root}（${payload.length} 个文件）`;
  }
  return payload.name;
}

async function readDirectoryEntry(
  entry: FileSystemEntry,
  prefix = "",
): Promise<File[]> {
  if (entry.isFile) {
    return new Promise((resolve) => {
      (entry as FileSystemFileEntry).file(
        (file) => {
          const rel = prefix ? `${prefix}/${file.name}` : file.name;
          Object.defineProperty(file, "webkitRelativePath", { value: rel });
          resolve([file]);
        },
        () => resolve([]),
      );
    });
  }
  if (!entry.isDirectory) return [];
  return new Promise((resolve) => {
    const reader = (entry as FileSystemDirectoryEntry).createReader();
    reader.readEntries(async (entries) => {
      const nested = await Promise.all(
        entries.map((child) =>
          readDirectoryEntry(child, prefix ? `${prefix}/${entry.name}` : entry.name),
        ),
      );
      resolve(nested.flat());
    });
  });
}

async function collectDroppedFiles(dataTransfer: DataTransfer): Promise<File[]> {
  const items = Array.from(dataTransfer.items || []);
  if (!items.length) return Array.from(dataTransfer.files || []);
  const fromEntries = (
    await Promise.all(
      items.map((item) => {
        const entry = item.webkitGetAsEntry?.();
        return entry ? readDirectoryEntry(entry) : Promise.resolve([]);
      }),
    )
  ).flat();
  if (fromEntries.length) return fromEntries;
  return Array.from(dataTransfer.files || []);
}

function successMessage(result: SkillUploadResult): string {
  const recovered = result.recovered ?? [];
  const installedCount = result.skills.filter((skill) => skill.installed).length;
  if (recovered.length > 0) {
    const names = recovered.join("、");
    return installedCount > 0
      ? `技能已在库中，已安装「${names}」`
      : `技能「${names}」已在库中`;
  }
  if (installedCount > 0) {
    return `已上传并安装 ${installedCount} 个技能`;
  }
  return `已上传 ${result.uploaded} 个技能`;
}

async function recoverPoolConflicts(
  conflictNames: string[],
): Promise<SkillUploadResult> {
  const mountedSkills: SkillItem[] = [];
  for (const name of conflictNames) {
    await skillsApi.mountSkill(name, { scope: "agent" });
    mountedSkills.push({ name, description: "", body: "", installed: true, enabled: true });
  }
  return {
    uploaded: 0,
    recovered: conflictNames,
    skills: mountedSkills,
    mounted: true,
  };
}

export default function UploadSkillModal({
  open,
  onClose,
  onUploaded,
}: UploadSkillModalProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<SelectedUpload | null>(null);
  const [fileLabel, setFileLabel] = useState("未选择文件");
  const [autoInstallSafe, setAutoInstallSafe] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [conflictPrompt, setConflictPrompt] = useState<{
    message: string;
    skillNames: string[];
  } | null>(null);

  const reset = useCallback(() => {
    setSelected(null);
    setFileLabel("未选择文件");
    setAutoInstallSafe(true);
    setUploading(false);
    setDragOver(false);
    setConflictPrompt(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    if (folderInputRef.current) folderInputRef.current.value = "";
  }, []);

  const handleClose = () => {
    reset();
    onClose();
  };

  const finishUpload = (result: SkillUploadResult) => {
    message.success(successMessage(result));
    onUploaded?.(result);
    handleClose();
  };

  const pickUpload = (payload: SelectedUpload | null) => {
    setSelected(payload);
    setFileLabel(payload ? uploadLabel(payload) : "未选择文件");
  };

  const handleSubmit = async () => {
    if (!selected) {
      message.warning("请先选择要上传的文件夹、.md 或 .zip 文件");
      return;
    }
    setUploading(true);
    setConflictPrompt(null);
    try {
      const result = await skillsApi.uploadSkill(selected, autoInstallSafe);
      finishUpload(result);
    } catch (err) {
      const conflictDetail = parseSkillUploadConflictDetail(err);
      const conflictNames = (conflictDetail?.conflicts ?? [])
        .map((item) => item.skill_name)
        .filter(Boolean);
      if (autoInstallSafe && conflictNames.length > 0) {
        try {
          message.info("技能已在库中，正在安装…");
          const recovered = await recoverPoolConflicts(conflictNames);
          finishUpload(recovered);
          return;
        } catch (mountErr) {
          message.error(mountErr instanceof Error ? mountErr.message : String(mountErr));
          setUploading(false);
          return;
        }
      }
      if (conflictDetail?.conflicts?.length) {
        setConflictPrompt({
          message: formatSkillUploadConflictMessage(conflictDetail),
          skillNames: conflictNames,
        });
        setUploading(false);
        return;
      }
      if (err instanceof ApiError) {
        message.error(err.message);
      } else {
        message.error(err instanceof Error ? err.message : String(err));
      }
      setUploading(false);
    }
  };

  const handleInstallExisting = async () => {
    if (!conflictPrompt?.skillNames.length) return;
    setUploading(true);
    try {
      message.info("技能已在库中，正在安装…");
      const recovered = await recoverPoolConflicts(conflictPrompt.skillNames);
      finishUpload(recovered);
    } catch (err) {
      message.error(err instanceof Error ? err.message : String(err));
      setUploading(false);
    }
  };

  return (
    <Modal
      title={
        <div>
          <div className="text-lg font-semibold text-gray-900">上传技能</div>
          <p className="mt-1 text-[13px] font-normal text-gray-500">
            支持文件夹、.zip 或单文件 .md
          </p>
        </div>
      }
      open={open}
      onCancel={handleClose}
      width={560}
      destroyOnClose
      footer={
        <div className="flex items-center justify-end gap-2">
          {conflictPrompt ? (
            <>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-[13px] text-gray-700 hover:bg-gray-50"
              >
                取消
              </button>
              {autoInstallSafe ? null : (
                <button
                  type="button"
                  onClick={() => void handleInstallExisting()}
                  disabled={uploading}
                  className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-[13px] text-emerald-700 hover:bg-emerald-100 disabled:opacity-50"
                >
                  {uploading ? "安装中…" : "安装已有技能"}
                </button>
              )}
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-[13px] text-gray-700 hover:bg-gray-50"
              >
                取消
              </button>
              <button
                type="button"
                onClick={() => void handleSubmit()}
                disabled={uploading}
                className="rounded-lg wm-btn-primary px-4 py-2 text-[13px] disabled:opacity-50"
              >
                {uploading ? "上传中…" : "上传"}
              </button>
            </>
          )}
        </div>
      }
    >
      {conflictPrompt ? (
        <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
          <div className="font-medium">技能已存在</div>
          <p className="mt-2 leading-relaxed">{conflictPrompt.message}</p>
          {!autoInstallSafe ? (
            <p className="mt-2 text-amber-800">
              该技能已在技能库中。点击「安装已有技能」将其安装到当前员工工作区。
            </p>
          ) : null}
        </div>
      ) : null}

      <input
        ref={fileInputRef}
        type="file"
        accept=".md,.zip"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0] ?? null;
          pickUpload(file);
        }}
      />
      <input
        ref={folderInputRef}
        type="file"
        // @ts-expect-error webkitdirectory is non-standard but widely supported
        webkitdirectory=""
        directory=""
        multiple
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files || []);
          pickUpload(files.length ? files : null);
        }}
      />

      {!conflictPrompt ? (
        <>
          <div
            role="button"
            tabIndex={0}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragOver(false);
              void (async () => {
                const files = await collectDroppedFiles(e.dataTransfer);
                if (!files.length) return;
                if (files.length === 1) {
                  pickUpload(files[0]);
                  return;
                }
                pickUpload(files);
              })();
            }}
            onClick={(e) => {
              if (
                (e.target as HTMLElement).closest(
                  '[data-action="pick-skill-file"], [data-action="pick-skill-folder"]',
                )
              ) {
                return;
              }
              fileInputRef.current?.click();
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileInputRef.current?.click();
              }
            }}
            className={`flex h-[148px] cursor-pointer flex-col items-center justify-center rounded-xl border border-dashed text-gray-500 transition-colors ${
              dragOver ? "border-emerald-400 bg-emerald-50" : "border-gray-300 bg-gray-50"
            }`}
          >
            <div className="text-[32px]">⤴</div>
            <div className="mt-1 text-[14px]">拖拽文件夹/文件，或点击选择</div>
            <div className="mt-2 flex items-center gap-3 text-[12px] text-emerald-700">
              <button
                type="button"
                data-action="pick-skill-file"
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
                className="rounded-md border border-gray-200 bg-white px-2 py-1 hover:bg-gray-50"
              >
                选择文件
              </button>
              <button
                type="button"
                data-action="pick-skill-folder"
                onClick={(e) => {
                  e.stopPropagation();
                  folderInputRef.current?.click();
                }}
                className="rounded-md border border-gray-200 bg-white px-2 py-1 hover:bg-gray-50"
              >
                选择文件夹
              </button>
            </div>
            <div className="mt-2 text-[12px] text-gray-400">{fileLabel}</div>
          </div>

          <label className="mt-4 flex items-center gap-2 text-[13px] text-gray-600">
            <input
              type="checkbox"
              checked={autoInstallSafe}
              onChange={(e) => setAutoInstallSafe(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span>非高风险自动安装</span>
          </label>

          <div className="mt-4 text-[13px] text-gray-500">
            <div className="font-medium text-gray-700">文件要求</div>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              <li>支持文件夹、.zip 或单文件 .md</li>
              <li>必须包含 SKILL.md</li>
              <li>SKILL.md 需含 YAML 元数据：技能名称（name）与描述（description）</li>
            </ul>
          </div>
        </>
      ) : null}
    </Modal>
  );
}
