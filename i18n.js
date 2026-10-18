(function initializeI18n(global) {
  // Visitor-facing English/Chinese switch. English stays in the HTML and
  // scripts; in Chinese, any text node or label whose full text matches an
  // entry below is replaced, including text rendered later by other scripts.
  // Photographer-entered content (titles, introductions, tags) is never
  // translated. Chinese copy is a first draft for the photographer to review.
  const STORAGE_KEY = "mt-presence-language";
  const SUPPORTED = ["en", "zh"];
  const TRANSLATED_ATTRIBUTES = ["placeholder", "aria-label", "title"];
  const SKIP_SELECTOR = "script, style, template, textarea, [data-i18n-skip]";

  const ZH = {
    // Page titles
    "MT Presence | Fine Art Photography": "MT Presence | 艺术摄影",
    "Works Archive | MT Presence": "作品 | MT Presence",
    "Work | MT Presence": "作品 | MT Presence",
    "About | MT Presence": "关于 | MT Presence",
    "Contact Artist | MT Presence": "联系艺术家 | MT Presence",
    "Privacy | MT Presence": "隐私说明 | MT Presence",
    "Terms of Use | MT Presence": "使用条款 | MT Presence",

    // Header and navigation
    "Home": "首页",
    "Works": "作品",
    "About": "关于",
    "Contact": "联系",
    "Primary": "主导航",
    "MT Presence home": "MT Presence 首页",
    "Open navigation": "打开导航",
    "Close navigation": "关闭导航",
    "Search works, artists, tags": "搜索作品、艺术家、标签",
    "Search works, artists, and tags": "搜索作品、艺术家和标签",
    "Search the archive": "搜索作品",
    "Search suggestions": "搜索建议",
    "Searching archive…": "正在搜索…",
    "No matching works.": "没有找到匹配的作品。",
    "Search is temporarily unavailable.": "搜索暂时不可用。",
    "Search is unavailable.": "搜索不可用。",
    "Published work": "已发布作品",
    "Untitled work": "未命名作品",
    "Language": "语言",

    // Footer
    "Inquiries": "合作咨询",
    "Exhibitions, licensing, and commissions.": "展览、授权与委托创作。",
    "For presentations, image use, and considered collaborations, begin a conversation with the artist.": "如需展览、作品使用授权或合作，欢迎与艺术家联系。",
    "Contact Artist": "联系艺术家",
    "Fine art photography for long looking.": "值得长久凝视的艺术摄影。",
    "Explore": "浏览",
    "Privacy": "隐私说明",
    "Practice": "合作",
    "Exhibition inquiries": "展览咨询",
    "Licensing": "作品授权",
    "Commissions": "委托创作",
    "All rights reserved.": "保留所有权利。",
    "Public Works": "公开作品",

    // Home
    "Abstract Field": "抽象之境",
    "A Quiet Field for Images": "影像的静谧之境",
    "Images are not records of the world. They are encounters held in the present space between the artist and the viewer.": "影像不是对世界的记录，而是艺术家与观者在当下相遇的空间。",
    "Concrete Field": "具象之境",
    "Where Looking Becomes Presence": "凝视，成为在场",
    "Light, weather, and distance settle into form. Each photograph opens a quiet place for the viewer to stay.": "光线、天气与距离沉淀为形。每一幅作品，都为观者留出一处可以停留的安静之地。",
    "Enter Works": "进入作品",
    "About the Practice": "关于创作",
    "Selected Works": "精选作品",
    "Pause motion": "暂停滚动",
    "Resume motion": "继续滚动",
    "Statement": "创作理念",
    "MT Presence is a fine art photography practice by MT, shaped around quiet images, long looking, and the space between abstraction and the visible world.": "MT Presence 是 MT 的艺术摄影创作，关注安静的影像、长久的凝视，以及抽象与可见世界之间的空间。",
    "The work does not treat photography as simple documentation. It uses landscape, weather, surface, and distance to hold a moment before it becomes explanation.": "这些作品并不把摄影当作简单的记录，而是借由风景、天气、表面与距离，留住那个尚未被解释的瞬间。",
    "Each image is made as an encounter: something to return to, collect, live with, and see differently over time.": "每一幅影像都是一次相遇：值得反复回看、收藏、与之相处，并随时间看出不同。",
    "Enter the archive and spend time with the work.": "进入作品，与它们共度一段时光。",
    "Homepage statement image.": "首页创作理念配图。",

    // Works archive and viewer
    "Type": "类型",
    "All Works": "全部作品",
    "Abstract": "抽象",
    "Concrete": "具象",
    "Ratio": "比例",
    "All Ratios": "全部比例",
    "Square": "方形",
    "Classic": "经典",
    "Portrait": "竖幅",
    "Vertical": "竖长",
    "Landscape": "横幅",
    "Cinema": "宽银幕",
    "Panorama": "全景",
    "Works Archive": "作品",
    "Loading archive.": "正在加载作品。",
    "Retry loading works": "重新加载作品",
    "No works match this search.": "没有符合搜索条件的作品。",
    "No published works yet.": "暂无已发布的作品。",
    "The archive is being prepared. New work will appear here soon.": "作品正在整理中，新作品即将在这里展出。",
    "Published works are temporarily unavailable.": "作品暂时无法加载。",
    "Published works are temporarily unavailable. Please retry.": "作品暂时无法加载，请重试。",
    "Loading works timed out. Please retry.": "加载作品超时，请重试。",
    "The archive returned an invalid response. Please retry.": "作品数据异常，请重试。",
    "The archive contains no published works.": "暂无已发布的作品。",
    "Archive unavailable": "作品暂时不可用",
    "Work viewer": "作品查看器",
    "Fit": "适应屏幕",
    "Fit image to screen": "图片适应屏幕",
    "Fit to window": "适应窗口",
    "Actual size": "原始尺寸",
    "View actual size": "查看原始尺寸",
    "Show details": "显示信息",
    "Hide details": "隐藏信息",
    "Show work details": "显示作品信息",
    "Hide work details": "隐藏作品信息",
    "Inquire": "咨询",
    "Tags": "标签",
    "Related Works": "相关作品",
    "Artist Statement": "艺术家自述",
    "Description": "作品说明",
    "Size": "尺寸",
    "Captured": "拍摄时间",
    "Undated": "未注明日期",
    "Unknown": "未知",
    "Work": "作品",
    "Subject": "题材",
    "Mood": "氛围",
    "Light": "光线",
    "Place": "地点",
    "Color": "彩色",
    "Black and white": "黑白",
    "Monochrome": "单色",

    // Work detail
    "Loading work": "正在加载作品",
    "Work unavailable": "作品不可用",
    "This work is unavailable.": "这件作品暂时无法查看。",
    "No published works are available.": "暂无已发布的作品。",
    "Return to Works": "返回作品",

    // About
    "MT works between abstraction and the visible world. The photographs begin with real places and objects, then stay with the point at which description becomes uncertain: a shoreline held in fog, a plane of stone, or light crossing an ordinary form.": "MT 的创作游走于抽象与可见世界之间。作品始于真实的地点与物体，并停留在描述开始变得模糊的那一刻：雾中的海岸线、一片石面，或掠过寻常形体的光。",
    "A fine art photography practice concerned with weather, surface, distance, and the time required to look.": "一种关注天气、表面、距离，以及凝视所需时间的艺术摄影实践。",
    "The resulting photographs are restrained and enduring, intended to be lived with, studied over time, and passed on.": "这些作品克制而持久，适合长久相伴、慢慢品读，并得以传承。",
    "Based in USA": "常驻美国",
    "Working from a quiet studio, with projects worldwide.": "在安静的工作室中创作，项目遍及世界各地。",
    "Available for commissions": "接受委托创作",
    "Limited editorial, private, and collaborative assignments.": "承接少量出版、私人及合作项目。",
    "Working internationally": "国际合作",
    "Projects, exhibitions, and conversations across continents.": "跨越各大洲的项目、展览与交流。",
    "Read the artist statement": "阅读艺术家自述",

    // Contact
    "For exhibitions, editorial projects, licensing, print inquiries, and considered commissions.": "展览、出版项目、作品授权、版画购买与委托创作，欢迎来信咨询。",
    "Name": "姓名",
    "Email": "邮箱",
    "Inquiry Type": "咨询类型",
    "Select an inquiry type": "请选择咨询类型",
    "Exhibition": "展览",
    "Editorial": "出版",
    "Print": "版画购买",
    "Commission": "委托创作",
    "Other": "其他",
    "Organization": "机构",
    "Optional": "选填",
    "Project / Intended Use": "项目 / 用途",
    "Timeline": "时间安排",
    "Budget Range": "预算范围",
    "Selected Works": "已选作品",
    "Selected Work": "已选作品",
    "Series inquiry": "系列咨询",
    "Message": "留言",
    "Your name, email address, and message are stored to handle this inquiry.": "你的姓名、邮箱和留言仅用于处理本次咨询。",
    "Privacy notice": "隐私说明",
    "Submit Inquiry": "提交咨询",
    "Recording inquiry...": "正在提交…",
    "Inquiry recorded": "咨询已提交",
    "Reference": "编号",
    "Start another inquiry": "再提交一条咨询",
    "Remove": "移除",
    "Pending": "待处理",
    "Loading selection...": "正在加载所选作品…",
    "Selection unavailable": "所选作品不可用",
    "Name is required.": "请填写姓名。",
    "Email is required.": "请填写邮箱。",
    "Enter a valid email address.": "请输入有效的邮箱地址。",
    "Select an inquiry type.": "请选择咨询类型。",
    "Project or intended use is required.": "请填写项目或用途。",
    "Message is required.": "请填写留言。",
    "Enter at least 5 characters.": "请至少输入 5 个字。",
    "Enter at least 10 characters.": "请至少输入 10 个字。",
    "The inquiry could not be recorded.": "咨询提交失败，请稍后重试。",
    "Security verification is unavailable.": "安全验证暂时不可用，请稍后重试。",
    "Selected works are unavailable.": "所选作品不可用。",
    "The selected works are no longer available.": "所选作品已不可用。",
    "Unable to load the selected works. Return to Works and try again.": "无法加载所选作品，请返回作品页重试。",
    "Wait for the selected works to load before continuing.": "请等所选作品加载完成后再继续。",
    "Limit the inquiry selection to 10 works.": "每次咨询最多选择 10 件作品。",
    "Your name": "你的姓名",
    "you@example.com": "you@example.com",
    "Studio, gallery, publication...": "工作室、画廊、出版机构……",
    "How would you like to work with the images?": "你希望如何使用这些作品？",
    "Month or date range": "月份或日期范围",
    "Expected range": "预期范围",
    "Share the context, scope, and any details that would help begin the conversation.": "请简单介绍背景、范围以及有助于沟通的细节。",
    "Website": "网站",

    // Labels read by screen readers
    "Primary navigation": "主导航",
    "Primary actions": "主要操作",
    "Site footer": "网站页脚",
    "Archive filters": "作品筛选",
    "Work viewer controls": "查看器控制",
    "Previous work": "上一件作品",
    "Next work": "下一件作品",
    "Close work viewer": "关闭查看器",
    "Image viewing area": "图片查看区域",
    "Work details": "作品信息",
    "Work actions": "作品操作",
    "Selected AI generated landscape works": "精选作品",
    "Published works loaded.": "作品已加载。",
    "Practice information": "创作信息",
    "Browse works": "浏览作品",
  };

  // Dynamic messages that carry numbers or work titles.
  const ZH_PATTERNS = [
    [/^(\d+) of (\d+) works?(?: \/ (.+))?$/, (match, shown, total, filters) => (
      `显示 ${shown} / 共 ${total} 件作品${filters ? `（${filters.split(" + ").map((part) => ZH[part] || part).join(" + ")}）` : ""}`
    )],
    [/^Open full-screen viewer for (.+)$/, (match, title) => `全屏查看《${title}》`],
    [/^View details for (.+)$/, (match, title) => `查看《${title}》详情`],
    // Too broad for page text (a title may start with "View"); labels only.
    [/^View (.+)$/, (match, title) => `查看《${title}》`, { attributesOnly: true }],
    [/^Remove (.+) from this inquiry$/, (match, title) => `从本次咨询中移除《${title}》`, { attributesOnly: true }],
  ];

  function storedLanguage() {
    try {
      return global.localStorage.getItem(STORAGE_KEY);
    } catch (_error) {
      return null;
    }
  }

  function detectLanguage() {
    const stored = storedLanguage();
    if (SUPPORTED.includes(stored)) return stored;
    const preferred = global.navigator.languages?.length ? global.navigator.languages : [global.navigator.language];
    return preferred.some((tag) => /^zh\b/i.test(String(tag || ""))) ? "zh" : "en";
  }

  const language = detectLanguage();

  function translate(text, { attribute = false } = {}) {
    if (language !== "zh" || typeof text !== "string") return text;
    const trimmed = text.trim();
    // HTML source wraps long sentences; compare with whitespace collapsed.
    const normalized = trimmed.replace(/\s+/g, " ");
    let translated = Object.prototype.hasOwnProperty.call(ZH, normalized) ? ZH[normalized] : null;
    if (!translated) {
      for (const [pattern, render, options = {}] of ZH_PATTERNS) {
        if (options.attributesOnly && !attribute) continue;
        const match = normalized.match(pattern);
        if (match) {
          translated = render(...match);
          break;
        }
      }
    }
    return translated ? text.replace(trimmed, translated) : text;
  }

  function t(english) {
    return translate(english);
  }

  function skipped(node) {
    const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
    return !element || Boolean(element.closest(SKIP_SELECTOR));
  }

  function translateElementAttributes(element) {
    TRANSLATED_ATTRIBUTES.forEach((name) => {
      const value = element.getAttribute(name);
      if (value) {
        const translated = translate(value, { attribute: true });
        if (translated !== value) element.setAttribute(name, translated);
      }
    });
  }

  function translateTree(root) {
    if (language !== "zh" || !root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      if (!skipped(root)) {
        const translated = translate(root.nodeValue);
        if (translated !== root.nodeValue) root.nodeValue = translated;
      }
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_NODE) return;
    if (root.nodeType === Node.ELEMENT_NODE) {
      if (skipped(root)) return;
      translateElementAttributes(root);
    }
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (node.nodeType === Node.ELEMENT_NODE && node.matches(SKIP_SELECTOR)) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      },
    });
    let node = walker.nextNode();
    while (node) {
      if (node.nodeType === Node.TEXT_NODE) {
        const translated = translate(node.nodeValue);
        if (translated !== node.nodeValue) node.nodeValue = translated;
      } else {
        translateElementAttributes(node);
      }
      node = walker.nextNode();
    }
  }

  function setLanguage(next) {
    if (!SUPPORTED.includes(next) || next === language) return;
    try {
      global.localStorage.setItem(STORAGE_KEY, next);
    } catch (_error) {
      // Without storage the choice lasts for this page only.
    }
    global.location.reload();
  }

  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  document.documentElement.dataset.language = language;
  global.MTPresenceI18n = Object.freeze({ language, t, setLanguage, supported: SUPPORTED.slice() });

  if (language === "zh") {
    document.title = translate(document.title);
    translateTree(document.body);
    // Scripts render navigation, footer, filters and messages after load.
    new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === "characterData") {
          translateTree(mutation.target);
        } else if (mutation.type === "attributes") {
          if (!skipped(mutation.target)) translateElementAttributes(mutation.target);
        } else {
          mutation.addedNodes.forEach((node) => translateTree(node));
        }
      });
    }).observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: TRANSLATED_ATTRIBUTES,
    });
  }
})(window);
