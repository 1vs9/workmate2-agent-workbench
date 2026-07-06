import { useCallback, useEffect, useMemo, useState } from "react";

import {
  Button,
  Form,
  Input,
  Modal,
  Space,
  Steps,
  Typography,
  message,
} from "antd";

import { CheckCircleOutlined } from "@ant-design/icons";

import { useAsyncList } from "../../hooks/useAsyncList";

import { skillsApi, type SkillItem } from "../../api/skills";
import SkillPickerField from "../skills/SkillPickerField";
import {
  EMPLOYEE_WIZARD_STEPS,
  buildEmployeeDesc,
  suggestEmployeeSkills,
  validateEmployeeCreateValues,
  type EmployeeCreateFormValues,
} from "../../utils/employeeCreate";

import { executeEmployeeCreateWizard } from "../../utils/employeeCreateWizard";

import { useReferenceDataStore } from "../../store/referenceDataStore";



interface EmployeeCreateWizardProps {

  open: boolean;

  onClose: () => void;

  onCreated?: (result: { name: string }) => void;

}



type WizardPhase = "form" | "success";



export default function EmployeeCreateWizard({

  open,

  onClose,

  onCreated,

}: EmployeeCreateWizardProps) {

  const [step, setStep] = useState(0);

  const [phase, setPhase] = useState<WizardPhase>("form");

  const [submitting, setSubmitting] = useState(false);

  const [createdName, setCreatedName] = useState("");

  const [form] = Form.useForm<EmployeeCreateFormValues>();



  const skillsLoader = useCallback(() => skillsApi.listSkills(), []);

  const { data: skills } = useAsyncList<SkillItem>(skillsLoader);



  const poolSkills = useMemo(

    () => skills.filter((s) => s.installed !== false),

    [skills],

  );



  const resetWizard = useCallback(() => {

    setStep(0);

    setPhase("form");

    setCreatedName("");

    setSubmitting(false);

    form.resetFields();

    form.setFieldsValue({ skillNames: [] });

  }, [form]);



  useEffect(() => {

    if (open) {

      resetWizard();

    }

  }, [open, resetWizard]);



  const handleClose = () => {

    onClose();

  };



  const validateCurrentStep = async (): Promise<boolean> => {

    if (step === 0) {

      try {

        await form.validateFields(["name", "specialty", "background"]);

        const values = form.getFieldsValue();

        const err = validateEmployeeCreateValues(values);

        if (err) {

          message.warning(err);

          return false;

        }

        return true;

      } catch {

        return false;

      }

    }

    return true;

  };



  const handleNext = async () => {
    const ok = await validateCurrentStep();
    if (!ok) return;
    if (step === 0) {
      const values = form.getFieldsValue();
      const current = (values.skillNames ?? []).filter(Boolean);
      if (current.length === 0) {
        form.setFieldsValue({
          skillNames: suggestEmployeeSkills(values.specialty ?? "", values.background ?? ""),
        });
      }
    }
    setStep((s) => Math.min(s + 1, EMPLOYEE_WIZARD_STEPS.length - 1));
  };



  const handlePrev = () => {

    setStep((s) => Math.max(s - 1, 0));

  };



  const handleSubmit = async () => {

    const values = form.getFieldsValue();

    const err = validateEmployeeCreateValues(values);

    if (err) {

      message.warning(err);

      return;

    }



    setSubmitting(true);

    try {

      const result = await executeEmployeeCreateWizard(values);

      setCreatedName(result.name);

      setPhase("success");

      // Refresh the shared cache so the new employee appears in composer / chat
      // dropdowns without waiting for the freshness window to elapse.
      useReferenceDataStore.getState().invalidate();

      onCreated?.({ name: result.name });

      message.success(`「${result.name}」已创建并加入员工列表`);

    } catch (submitErr) {

      message.error(submitErr instanceof Error ? submitErr.message : String(submitErr));

    } finally {

      setSubmitting(false);

    }

  };



  const previewValues = Form.useWatch([], form) as Partial<EmployeeCreateFormValues>;

  const previewDesc = buildEmployeeDesc({

    specialty: previewValues?.specialty ?? "",

    background: previewValues?.background ?? "",

  });



  const footer =

    phase === "success" ? (

      <Button type="primary" onClick={handleClose}>

        完成

      </Button>

    ) : step < EMPLOYEE_WIZARD_STEPS.length - 1 ? (

      <Space>

        <Button onClick={handleClose}>取消</Button>

        {step > 0 ? <Button onClick={handlePrev}>上一步</Button> : null}

        <Button type="primary" onClick={() => void handleNext()}>

          下一步

        </Button>

      </Space>

    ) : (

      <Space>

        <Button onClick={handleClose}>取消</Button>

        <Button onClick={handlePrev}>上一步</Button>

        <Button type="primary" loading={submitting} onClick={() => void handleSubmit()}>

          确认创建

        </Button>

      </Space>

    );



  return (

    <Modal

      title="添加员工"

      open={open}

      onCancel={handleClose}

      footer={footer}

      width={560}

      destroyOnClose

    >

      {phase === "success" ? (

        <div className="py-6 text-center">

          <CheckCircleOutlined className="mb-3 text-4xl text-emerald-500" />

          <Typography.Title level={5} className="!mb-2">

            员工创建成功

          </Typography.Title>

          <Typography.Paragraph type="secondary" className="!mb-0">

            「{createdName}」已加入岗位智能体与员工列表。可在本页查看卡片，或通过「派发任务」开始使用。

          </Typography.Paragraph>

        </div>

      ) : (

        <>

          <Steps

            size="small"

            current={step}

            items={EMPLOYEE_WIZARD_STEPS.map((s) => ({

              title: s.title,

              description: s.description,

            }))}

            className="mb-6"

          />



          <Form

            form={form}

            layout="vertical"

            preserve={false}

            initialValues={{ skillNames: [] }}

          >

            {step === 0 ? (

              <>

                <Form.Item

                  name="name"

                  label="员工名称"

                  rules={[{ required: true, message: "请输入员工名称" }]}

                  extra="如：销售助理、舆情分析专家"

                >

                  <Input placeholder="输入岗位名称" />

                </Form.Item>

                <Form.Item

                  name="specialty"

                  label="擅长领域"

                  rules={[{ required: true, message: "请填写擅长领域" }]}

                >

                  <Input.TextArea

                    rows={2}

                    placeholder="该员工擅长的任务类型与能力，如：监测社媒、撰写日报"

                  />

                </Form.Item>

                <Form.Item

                  name="background"

                  label="经验背景"

                  rules={[{ required: true, message: "请填写经验背景" }]}

                >

                  <Input.TextArea

                    rows={2}

                    placeholder="行业背景、年限、相关经验等"

                  />

                </Form.Item>

              </>

            ) : null}



            {step === 1 ? (
              <Form.Item name="skillNames">
                <SkillPickerField
                  label="挂载技能（可选）"
                  skills={poolSkills}
                  emptyHint="点击「添加」选择技能；未选时将按专长自动推荐"
                  modalTitle="选择要挂载的技能"
                />
              </Form.Item>
            ) : null}



            {step === 2 ? (

              <div className="rounded-lg border border-gray-100 bg-gray-50/80 p-4 text-sm">

                <Typography.Text type="secondary" className="mb-3 block">

                  请确认以下信息，点击「确认创建」后将写入岗位智能体并加入员工列表。

                </Typography.Text>

                <dl className="space-y-2">

                  <div className="flex gap-2">

                    <dt className="w-20 shrink-0 text-gray-500">名称</dt>

                    <dd className="font-medium text-gray-900">{previewValues?.name || "—"}</dd>

                  </div>

                  <div className="flex gap-2">

                    <dt className="w-20 shrink-0 text-gray-500">职责</dt>

                    <dd className="text-gray-800">{previewDesc || "—"}</dd>

                  </div>

                  <div className="flex gap-2">

                    <dt className="w-20 shrink-0 text-gray-500">技能</dt>

                    <dd>

                      {(previewValues?.skillNames ?? []).length

                        ? (previewValues?.skillNames ?? []).join(", ")

                        : "无"}

                    </dd>

                  </div>

                </dl>

              </div>

            ) : null}

          </Form>

        </>

      )}

    </Modal>

  );

}


