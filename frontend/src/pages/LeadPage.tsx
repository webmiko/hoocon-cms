import { Breadcrumbs } from "../components/Breadcrumbs";
import { LeadForm } from "../components/LeadForm";
import { Seo } from "../components/Seo";
import styles from "./LeadPage.module.css";

type LeadType = "consultation" | "replacement";

const COPY: Record<
  LeadType,
  {
    title: string;
    intro: string;
    seoDescription: string;
    steps: Array<{ title: string; text: string }>;
    after: string;
  }
> = {
  consultation: {
    title: "Запрос консультации и КП",
    intro:
      "Опишите задачу или пришлите спецификацию — инженер подберёт привод по " +
      "моменту, напряжению и сигналу управления и подготовит коммерческое " +
      "предложение.",
    seoDescription:
      "Консультация инженера Hoocon и запрос КП: подбор привода ОВК по ТТХ, " +
      "ответ до 2 рабочих часов.",
    steps: [
      {
        title: "Что указать в заявке",
        text:
          "Момент (Н·м), напряжение, тип возвратной пружины, сигнал управления, " +
          "количество и срок поставки — чем точнее, тем быстрее КП.",
      },
      {
        title: "Что будет после отправки",
        text:
          "Ответим до 2 рабочих часов: либо готовый расчёт, либо уточняющие " +
          "вопросы. Паспорта и сертификаты приложим по запросу.",
      },
      {
        title: "Без корзины и публичного прайса",
        text:
          "Цена зависит от объёма и комплектации. Готовим КП под вашу " +
          "спецификацию — как для проекта, так и для разовой замены.",
      },
    ],
    after: "Форма ниже уходит на sales@hoocon.ru. Срок ответа — до 2 рабочих часов.",
  },
  replacement: {
    title: "Подбор аналога Belimo",
    intro:
      "Укажите код привода Belimo — подберём совместимый аналог Hoocon по " +
      "моменту, напряжению и сигналу. Если точного кода нет, опишите задачу.",
    seoDescription:
      "Замена Belimo на аналог Hoocon: подбор по коду и ТТХ, ответ до 2 " +
      "рабочих часов.",
    steps: [
      {
        title: "Что указать",
        text:
          "Код Belimo (например LM24A-SR), напряжение, момент и тип управления. " +
          "Если код неизвестен — фото шильдика или ТТХ из проекта.",
      },
      {
        title: "Что получите",
        text:
          "Рекомендованный артикул Hoocon, краткое сравнение по ключевым " +
          "параметрам и, по запросу, КП со сроком отгрузки со склада в Москве.",
      },
      {
        title: "Срок ответа",
        text:
          "До 2 рабочих часов в рабочие дни. Срочные замены на объекте — " +
          "отметьте в сообщении, приоритет отдадим таким заявкам.",
      },
    ],
    after: "Форма ниже уходит на sales@hoocon.ru. Срок ответа — до 2 рабочих часов.",
  },
};

interface LeadPageProps {
  leadType: LeadType;
}

/**
 * Standalone lead page for consultation / replacement requests.
 *
 * RFQ is handled inline on the SKU detail page (SkuDetailPage).
 * Spec: ПЛАН §6 Iter 4; docs/security-baseline.md §3; БЗ §9.6 оффер.
 */
export function LeadPage({ leadType }: LeadPageProps) {
  const copy = COPY[leadType];

  return (
    <div className={styles.page}>
      <Seo
        title={copy.title}
        description={copy.seoDescription}
        path={`/${leadType}`}
        noindex
      />
      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          ...(leadType === "replacement"
            ? [{ label: "Каталог", to: "/catalog" }]
            : []),
          { label: copy.title },
        ]}
      />

      <header className={styles.header}>
        <h1 className={styles.title}>{copy.title}</h1>
        <p className={styles.intro}>{copy.intro}</p>
      </header>

      <ol className={styles.steps}>
        {copy.steps.map((step) => (
          <li key={step.title} className={styles.step}>
            <h2 className={styles.stepTitle}>{step.title}</h2>
            <p className={styles.stepText}>{step.text}</p>
          </li>
        ))}
      </ol>

      <p className={styles.afterNote}>{copy.after}</p>

      <div className={styles.formCard}>
        <LeadForm leadType={leadType} />
      </div>
    </div>
  );
}
