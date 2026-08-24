    window.addEventListener("DOMContentLoaded", () => {
      const data = window.CSARC_SITE_CONTENT;
      if (!data) {
        document.querySelector("main").textContent = "找不到 docs/site-content.js。";
        return;
      }

      const text = (selector, value) => {
        document.querySelector(selector).textContent = value;
      };
      const list = (selector, values) => {
        const root = document.querySelector(selector);
        for (const value of values) {
          const item = document.createElement("span");
          item.className = "badge";
          item.textContent = value;
          root.append(item);
        }
      };

      text("#project-name", data.project.name);
      text("#project-description", data.project.description);
      list("#project-badges", [data.project.stage, data.project.language, `${data.project.branch} flow`, data.project.owner]);
      list("#prerequisites", data.start.prerequisites);
      text("#commands", data.start.commands.join("\n"));
      text("#release-current", data.release.current);
      text("#release-optional", data.release.optional);
      text("#update", data.release.update);

      const structure = document.querySelector("#structure-body");
      for (const row of data.structure) {
        const tr = document.createElement("tr");
        for (const value of [row.path, row.purpose, row.owner]) {
          const td = document.createElement("td");
          td.textContent = value;
          tr.append(td);
        }
        structure.append(tr);
      }

      for (const item of data.workflow) {
        const article = document.createElement("article");
        article.className = "card";
        const title = document.createElement("strong");
        title.textContent = item.title;
        const detail = document.createElement("p");
        detail.textContent = item.detail;
        article.append(title, detail);
        document.querySelector("#workflow-cards").append(article);
      }

      const safeguards = document.querySelector("#safeguards");
      for (const value of data.safeguards) {
        const li = document.createElement("li");
        li.textContent = value;
        safeguards.append(li);
      }
    });
