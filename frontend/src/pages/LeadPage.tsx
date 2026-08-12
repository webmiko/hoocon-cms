import { useMemo } from "react";
import { useSearchParams } from "react-router-dom";

import { Breadcrumbs } from "../components/Breadcrumbs";
import { LeadForm } from "../components/LeadForm";
import { Seo } from "../components/Seo";
import styles from "./LeadPage.module.css";

type LeadType = "rfq" | "consultation" | "replacement";

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
  rfq: {
    title: "Запрос коммерческого предложения",
    intro:
      "Укажите компанию и контакты — подготовим КП по выбранным артикулам. "
      + "Несколько заявок с одной компанией и одним именем менеджер "
      + "обработает как одно КП.",
    seoDescription:
      "Запрос КП на электроприводы и арматуру Hoocon: ответ до 2 рабочих часов.",
    steps: [
      {
        title: "Компания и имя",
        text:
          "Одинаковые компания и имя связывают заявки в одну нить КП. "
          + "Нужны отдельные КП — укажите разные компании.",
      },
      {
        title: "Артикулы",
        text:
          "Список позиций подставляется из сравнения или карточки. "
          + "Количество можно уточнить по каждой строке.",
      },
      {
        title: "Срок ответа",
        text:
          "До 2 рабочих часов: КП или уточняющие вопросы по характеристикам и объёму.",
      },
    ],
    after: "Форма ниже уходит на sales@hoocon.ru. Срок ответа — до 2 рабочих часов.",
  },
  consultation: {
    title: "Запрос консультации и КП",
    intro:
      "Опишите задачу или пришлите спецификацию — инженер подберёт привод по "
      + "моменту, напряжению и сигналу управления и подготовит коммерческое "
      + "предложение.",
    seoDescription:
      "Консультация инженера Hoocon и запрос КП: подбор привода вентиляции по "
      + "характеристикам, ответ до 2 рабочих часов.",
    steps: [
      {
        title: "Что указать в заявке",
        text:
          "Момент (Н·м), напряжение, тип возвратной пружины, сигнал управления, "
          + "количество и срок поставки — чем точнее, тем быстрее КП.",
      },
      {
        title: "Что будет после отправки",
        text:
          "Ответим до 2 рабочих часов: либо готовый расчёт, либо уточняющие "
          + "вопросы. Паспорта и сертификаты приложим по запросу.",
      },
      {
        title: "Без корзины и публичного прайса",
        text:
          "Цена зависит от объёма и комплектации. Готовим КП под вашу "
          + "спецификацию — как для проекта, так и для разовой замены.",
      },
    ],
    after: "Форма ниже уходит на sales@hoocon.ru. Срок ответа — до 2 рабочих часов.",
  },
  replacement: {
    title: "Подбор аналога Belimo",
    intro:
      "Укажите код привода Belimo — подберём совместимый аналог Hoocon по "
      + "моменту, напряжению и сигналу. Если точного кода нет, опишите задачу.",
    seoDescription:
      "Замена Belimo на аналог Hoocon: подбор по коду и характеристикам, ответ до 2 "
      + "рабочих часов.",
    steps: [
      {
        title: "Что указать",
        text:
          "Код Belimo (например LM24A-SR), напряжение, момент и тип управления. "
          + "Если код неизвестен — фото шильдика или характеристики из проекта.",
      },
      {
        title: "Что получите",
        text:
          "Рекомендованный артикул Hoocon, краткое сравнение по ключевым "
          + "параметрам и, по запросу, КП со сроком отгрузки со склада в Москве.",
      },
      {
        title: "Срок ответа",
        text:
          "До 2 рабочих часов в рабочие дни. Срочные замены на объекте — "
          + "отметьте в сообщении, приоритет отдадим таким заявкам.",
      },
    ],
    after: "Форма ниже уходит на sales@hoocon.ru. Срок ответа — до 2 рабочих часов.",
  },
};

interface LeadPageProps {
  leadType: LeadType;
}

/**
 * Standalone lead page for RFQ / consultation / replacement.
 *
 * PDP also embeds RFQ inline. Spec: ПЛАН §6 Iter 4.
 */
export function LeadPage({ leadType }: LeadPageProps) {
  const [searchParams] = useSearchParams();
  const skuCodes = useMemo(() => {
    const raw = searchParams.get("skus") || searchParams.get("sku") || "";
    return raw
      .split(",")
      .map((part) => part.trim())
      .filter(Boolean);
  }, [searchParams]);

  // Compare / ?skus= always goes through RFQ (structured items + company).
  const formType: LeadType =
    leadType === "consultation" && skuCodes.length > 0 ? "rfq" : leadType;
  const pageCopy = COPY[formType];
  const seoPath = formType === "rfq" ? "rfq" : leadType;

  return (
    <div className={styles.page}>
      <Seo
        title={pageCopy.title}
        description={pageCopy.seoDescription}
        path={`/${seoPath}`}
        noindex
      />
      <Breadcrumbs
        items={[
          { label: "Главная", to: "/" },
          ...(leadType === "replacement"
            ? [{ label: "Каталог", to: "/catalog" }]
            : []),
          { label: pageCopy.title },
        ]}
      />

      <header className={styles.header}>
        <h1 className={styles.title}>{pageCopy.title}</h1>
        <p className={styles.intro}>{pageCopy.intro}</p>
      </header>

      <ol className={styles.steps}>
        {pageCopy.steps.map((step) => (
          <li key={step.title} className={styles.step}>
            <h2 className={styles.stepTitle}>{step.title}</h2>
            <p className={styles.stepText}>{step.text}</p>
          </li>
        ))}
      </ol>

      <p className={styles.afterNote}>{pageCopy.after}</p>

      <div className={styles.formCard}>
        <LeadForm leadType={formType} skuCodes={skuCodes} />
      </div>
    </div>
  );
}
