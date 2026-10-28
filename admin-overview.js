(function initializeAdminOverview(global) {
  // 总览: what needs attention in image processing, visitor loading and the
  // database connection. Every block reads real data; a failing source shows
  // its own error instead of hiding the rest.
  const shell = global.MTAdminShell;
  const updated = document.querySelector("[data-overview-updated]");
  const issuesList = document.querySelector("[data-overview-issues]");
  const issuesCount = document.querySelector("[data-overview-issues-count]");
  const queueList = document.querySelector("[data-overview-queue]");
  const logList = document.querySelector("[data-overview-log]");
  const refreshButton = document.querySelector("[data-overview-refresh]");
  const LARGE_DISPLAY_BYTES = 2.5 * 1024 * 1024;
  const SLOW_SECONDS = 1.5;

  function setStatus(key, tone, text, title = "") {
    const block = document.querySelector(`[data-overview-status="${key}"]`);
    if (!block) return;
    block.querySelector(".admin-dot").dataset.tone = tone;
    block.querySelector("[data-status-text]").textContent = text;
    block.title = title;
  }

  function thumbElement(url) {
    const thumb = document.createElement("span");
    thumb.className = "admin-thumb";
    if (url) {
      const image = document.createElement("img");
      image.src = url;
      image.alt = "";
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("error", () => image.remove());
      thumb.append(image);
    }
    return thumb;
  }

  function messageItem(list, text) {
    const item = document.createElement("li");
    const message = document.createElement("p");
    message.className = "admin-empty";
    message.textContent = text;
    item.append(message);
    list.replaceChildren(item);
  }

  function workTitle(work) {
    return work.title || work.original_filename || "未命名作品";
  }

  // ----- 需要处理 --------------------------------------------------------------

  function collectIssues(works, slots) {
    const issues = [];
    works.forEach((work) => {
      const summary = work.asset_summary || {};
      const derivatives = work.derivatives || {};
      const thumb = work.thumbnail?.signed_url || "";
      const href = `/admin/works/${encodeURIComponent(work.id)}`;
      const name = `作品《${workTitle(work)}》`;
      if (Number(summary.flagged_count) > 0) issues.push({ thumb, href, tone: "bad", text: `${name} · 安全扫描未通过，不能发布` });
      else if (Number(summary.failed_count) > 0) issues.push({ thumb, href, tone: "bad", text: `${name} · 安全扫描失败，请重新上传` });
      else if (work.processing_status === "failed") issues.push({ thumb, href, tone: "bad", text: `${name} · 处理失败，请重新上传` });
      else if (work.publication_status === "published") {
        if (!derivatives.display || !derivatives.thumbnail) {
          issues.push({ thumb, href, tone: "warn", text: `${name} · 缺少${derivatives.display ? "缩略图" : "展示图"}` });
        } else if (Number(derivatives.display.byte_size) > LARGE_DISPLAY_BYTES) {
          issues.push({ thumb, href, tone: "warn", text: `${name} · 展示图 ${shell.formatBytes(derivatives.display.byte_size)}，网站加载偏慢` });
        }
      }
    });
    slots.forEach((slot) => {
      if (slot.live) return;
      issues.push({
        thumb: slot.work?.thumbnail?.signed_url || "",
        href: "/admin/site-images",
        tone: "warn",
        text: `${shell.SLOT_LABELS[slot.slot_key] || "网站图片位"} · 使用的《${workTitle(slot.work || {})}》已不在网站上，正在显示默认图`,
      });
    });
    return issues;
  }

  function renderIssues(issues) {
    issuesCount.textContent = issues.length ? `${issues.length} 项` : "";
    if (!issues.length) {
      messageItem(issuesList, "目前没有需要处理的图片。");
      return;
    }
    issuesList.replaceChildren(...issues.slice(0, 6).map((issue) => {
      const item = document.createElement("li");
      const text = document.createElement("p");
      text.className = "overview-issue-text";
      const dot = document.createElement("span");
      dot.className = "admin-dot";
      dot.dataset.tone = issue.tone;
      dot.style.marginRight = "10px";
      text.append(dot, issue.text);
      const link = document.createElement("a");
      link.className = "admin-link";
      link.href = issue.href;
      link.textContent = "去处理";
      item.append(thumbElement(issue.thumb), text, link);
      return item;
    }));
  }

  // ----- 处理队列 --------------------------------------------------------------

  function renderQueue(works) {
    const queue = works.filter((work) => {
      const stage = shell.imageStage(work);
      return stage.failed || stage.index < 3 || work.publication_status === "never_published";
    }).slice(0, 4);
    const processing = works.filter((work) => {
      const stage = shell.imageStage(work);
      return !stage.failed && stage.index < 3;
    }).length;
    setStatus(
      "processing",
      processing ? "warn" : "ok",
      processing ? `图片处理 · ${processing} 张处理中` : "图片处理 · 全部完成",
    );
    if (!queue.length) {
      messageItem(queueList, "没有正在处理或等待发布的图片。");
      return;
    }
    queueList.replaceChildren(...queue.map((work) => {
      const item = document.createElement("li");
      const body = document.createElement("div");
      body.className = "overview-queue-item";
      const name = document.createElement("p");
      name.textContent = work.original_filename || workTitle(work);
      body.append(name, shell.stepsElement(work));
      item.append(thumbElement(work.thumbnail?.signed_url || ""), body);
      return item;
    }));
  }

  // ----- 最近操作 --------------------------------------------------------------

  function describeAction(event) {
    const action = String(event.action || "");
    const slot = shell.SLOT_LABELS[event.target_id];
    if (action === "site_image.updated") return `更新网站图片位「${slot || event.target_id}」`;
    if (action === "site_image.reset") return `网站图片位「${slot || event.target_id}」恢复默认图`;
    if (action.includes("self_publish") || action.includes("publish")) return "发布作品到网站";
    if (action.includes("takedown") || action.includes("unpublish")) return "下架作品";
    if (action.includes("restore")) return "恢复作品";
    if (action.startsWith("conversation")) return "处理询价";
    if (action.includes("mfa")) return "两步验证设置";
    if (action.includes("profile")) return "更新个人资料";
    if (action.includes("export")) return "导出审计记录";
    return action.replace(/[._]/g, " ");
  }

  function renderLog(events) {
    if (!events.length) {
      messageItem(logList, "最近 30 天没有操作记录。");
      return;
    }
    logList.replaceChildren(...events.slice(0, 6).map((event) => {
      const item = document.createElement("li");
      const time = document.createElement("time");
      time.dateTime = event.created_at;
      time.textContent = shell.formatTime(event.created_at);
      const text = document.createElement("span");
      text.textContent = event.result === "failure" ? `${describeAction(event)}（未成功）` : describeAction(event);
      const actor = document.createElement("span");
      actor.textContent = `由 ${event.actor?.display_name || "系统"}`;
      item.append(time, text, actor);
      return item;
    }));
  }

  // ----- 网站加载: measured from this browser --------------------------------

  function timeImage(url) {
    return new Promise((resolve) => {
      const started = performance.now();
      const image = new Image();
      const done = (ok) => resolve(ok ? (performance.now() - started) / 1000 : null);
      image.onload = () => done(true);
      image.onerror = () => done(false);
      image.src = url;
    });
  }

  async function checkSite() {
    try {
      const started = performance.now();
      const payload = await shell.getJson("/api/archive/images?limit=12");
      const apiSeconds = (performance.now() - started) / 1000;
      const urls = (payload.items || []).map((item) => item.thumbnail_url || item.display_url).filter(Boolean).slice(0, 6);
      const timings = (await Promise.all(urls.map(timeImage))).filter((value) => value !== null);
      if (urls.length && !timings.length) {
        setStatus("site", "bad", "网站加载 · 作品图片无法加载");
        return;
      }
      const average = timings.length ? timings.reduce((sum, value) => sum + value, 0) / timings.length : apiSeconds;
      const slow = average > SLOW_SECONDS || apiSeconds > SLOW_SECONDS * 2;
      setStatus(
        "site",
        slow ? "warn" : "ok",
        `网站加载 · ${slow ? "偏慢" : "正常"}，平均 ${average < 0.1 ? "不到 0.1" : average.toFixed(1)} 秒`,
        `作品数据 ${apiSeconds.toFixed(2)} 秒；在本浏览器实测 ${timings.length} 张缩略图`,
      );
    } catch (_error) {
      setStatus("site", "bad", "网站加载 · 作品数据读取失败");
    }
  }

  // ----- Load everything --------------------------------------------------

  async function load() {
    refreshButton.disabled = true;
    updated.textContent = "正在读取…";
    const [worksResult, slotsResult, auditResult] = await Promise.allSettled([
      shell.getJson("/api/admin/works?limit=50&sort=updated_desc"),
      shell.getJson("/api/admin/site-images"),
      shell.getJson("/api/admin/audit?limit=6"),
    ]);
    const authError = [worksResult, slotsResult, auditResult].find((result) => result.status === "rejected")?.reason;
    if (authError && shell.redirectForAuth(authError)) return;

    const works = worksResult.status === "fulfilled" ? worksResult.value.items || [] : null;
    const slots = slotsResult.status === "fulfilled" ? slotsResult.value.items || [] : [];
    if (works) {
      const total = worksResult.value.counts?.all ?? works.length;
      setStatus("data", "ok", `后台数据 · 已同步 ${total} 件`);
      renderIssues(collectIssues(works, slots));
      renderQueue(works);
    } else {
      setStatus("data", "bad", "后台数据 · 读取失败");
      setStatus("processing", "bad", "图片处理 · 无法读取");
      messageItem(issuesList, "作品数据读取失败，请刷新重试。");
      messageItem(queueList, "作品数据读取失败，请刷新重试。");
    }
    if (auditResult.status === "fulfilled") renderLog(auditResult.value.items || []);
    else messageItem(logList, "操作记录读取失败。");
    updated.textContent = `今天 ${shell.formatTime(new Date(), { withDate: false })} 更新`;
    refreshButton.disabled = false;
    checkSite();
  }

  refreshButton.addEventListener("click", load);
  load();
})(window);
