# A股智选 - UI/UX 设计规范

> 版本: v1.0 | 日期: 2026-02-20

---

## 1. 设计理念

### 1.1 设计关键词

**专业 / 数据驱动 / 暗色沉浸 / 信息密度高 / 克制**

目标：像一个专业交易终端，但比传统券商软件更现代、更易读。不追求花哨效果，数据可读性和信息密度是第一优先级。

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **数据优先** | 图表和数字是主角，装饰元素最小化 |
| **暗色基底** | 减少长时间盯盘的视觉疲劳 |
| **红涨绿跌** | 遵循中国A股市场惯例（与西方相反） |
| **信息分层** | 核心数据大而醒目，辅助信息小而克制 |
| **一致性** | 同类数据用同一种视觉语言 |

---

## 2. 色彩体系

### 2.1 基础色板

#### 背景层级

| 角色 | 色值 | CSS变量 | 用途 |
|------|------|---------|------|
| 主背景 | `#0B0F19` | `--bg-primary` | 页面底色 |
| 卡片背景 | `#111827` | `--bg-card` | 卡片/面板 |
| 悬浮背景 | `#1F2937` | `--bg-elevated` | 下拉菜单/弹窗 |
| 输入框背景 | `#1A2332` | `--bg-input` | 表单输入 |

#### 文字层级

| 角色 | 色值 | CSS变量 | 用途 |
|------|------|---------|------|
| 主文字 | `#F1F5F9` | `--text-primary` | 标题/重要数据 |
| 次文字 | `#94A3B8` | `--text-secondary` | 说明文字/标签 |
| 弱文字 | `#64748B` | `--text-muted` | 时间戳/辅助信息 |
| 禁用文字 | `#475569` | `--text-disabled` | 不可用状态 |

#### 行情色（核心 - A股惯例）

| 角色 | 色值 | CSS变量 | 用途 |
|------|------|---------|------|
| **涨/看多** | `#EF4444` | `--color-up` | 涨幅、买入信号、红柱 |
| 涨-浅 | `#FCA5A5` | `--color-up-light` | 涨幅背景色 |
| 涨-深 | `#991B1B` | `--color-up-dark` | 涨幅暗色/K线实体 |
| **跌/看空** | `#22C55E` | `--color-down` | 跌幅、卖出信号、绿柱 |
| 跌-浅 | `#86EFAC` | `--color-down-light` | 跌幅背景色 |
| 跌-深 | `#166534` | `--color-down-dark` | 跌幅暗色/K线实体 |
| **平盘** | `#F8FAFC` | `--color-flat` | 持平，无涨跌 |

#### 功能色

| 角色 | 色值 | CSS变量 | 用途 |
|------|------|---------|------|
| 主色调 | `#3B82F6` | `--color-primary` | 导航激活态/链接/选中 |
| 主色调-浅 | `#60A5FA` | `--color-primary-light` | 悬浮态 |
| 主色调-深 | `#1E40AF` | `--color-primary-dark` | 按下态 |
| 强调色 | `#F59E0B` | `--color-accent` | CTA按钮/重要标记/评分高亮 |
| 警告色 | `#F97316` | `--color-warning` | 风险提示/注意 |
| 信息色 | `#06B6D4` | `--color-info` | 中性信息/工具提示 |

### 2.2 行情色使用规范

```
上涨 → 红色系 (#EF4444)
  - 涨幅百分比文字
  - K线阳线实体填充
  - MACD红柱
  - 资金净流入柱
  - 评分信号 ✅ 标记

下跌 → 绿色系 (#22C55E)
  - 跌幅百分比文字
  - K线阴线实体填充
  - MACD绿柱
  - 资金净流出柱
  - 评分信号 ❌ 标记

平盘 → 白色 (#F8FAFC)
  - 涨跌幅为0
  - 十字星K线

中性 → 琥珀色 (#F59E0B)
  - 评分信号 ⚠️ 标记
  - 注意事项
```

### 2.3 评分色阶

| 评分范围 | 颜色 | 色值 | 标签 |
|---------|------|------|------|
| ≥80 | 亮红 | `#EF4444` | 强烈看多 |
| 60-79 | 浅红 | `#F87171` | 偏多 |
| 40-59 | 琥珀 | `#F59E0B` | 中性观望 |
| 20-39 | 浅绿 | `#4ADE80` | 偏空 |
| <20 | 亮绿 | `#22C55E` | 强烈看空 |

### 2.4 热力图色阶

```
涨幅梯度（红色系 - 由浅到深）:
  +0.0~+1.0%  →  #7F1D1D (暗红)
  +1.0~+3.0%  →  #B91C1C (中红)
  +3.0~+5.0%  →  #DC2626 (亮红)
  +5.0~+7.0%  →  #EF4444 (鲜红)
  +7.0%+      →  #F87171 (最亮红)

跌幅梯度（绿色系 - 由浅到深）:
  -0.0~-1.0%  →  #14532D (暗绿)
  -1.0~-3.0%  →  #166534 (中绿)
  -3.0~-5.0%  →  #16A34A (亮绿)
  -5.0~-7.0%  →  #22C55E (鲜绿)
  -7.0%+      →  #4ADE80 (最亮绿)

平盘:
  0%          →  #374151 (深灰)
```

---

## 3. 字体系统

### 3.1 字体选择

| 角色 | 字体 | 回退 | 用途 |
|------|------|------|------|
| **数据字体** | Fira Code | monospace | 数字/价格/代码/评分 |
| **界面字体** | Fira Sans | system-ui, sans-serif | 标签/说明/导航 |
| **中文回退** | - | "PingFang SC", "Microsoft YaHei" | 中文显示 |

### 3.2 CSS 引入

```css
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

:root {
  --font-data: 'Fira Code', 'SF Mono', 'Consolas', monospace;
  --font-ui: 'Fira Sans', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;
}
```

### 3.3 字号规范

| Token | 大小 | 行高 | 字重 | 用途 |
|-------|------|------|------|------|
| `--text-4xl` | 36px | 1.2 | 700 | 页面大标题 |
| `--text-3xl` | 30px | 1.2 | 700 | 指数价格 |
| `--text-2xl` | 24px | 1.3 | 600 | 卡片标题/个股价格 |
| `--text-xl` | 20px | 1.4 | 600 | 子标题 |
| `--text-lg` | 18px | 1.5 | 500 | 重要数据 |
| `--text-base` | 16px | 1.6 | 400 | 正文/表格数据 |
| `--text-sm` | 14px | 1.5 | 400 | 次要文字/标签 |
| `--text-xs` | 12px | 1.4 | 400 | 时间戳/注释 |

### 3.4 数字显示规则

```
价格:    保留2位小数，等宽数字，右对齐    ¥1,856.00
涨跌幅:  带正负号，保留2位小数，带%        +2.35%  -1.08%
成交量:  千分位分隔，缩写大数字            1.23亿  8,456万
评分:    整数或1位小数                     87.5分  92分
百分比:  保留1位小数                       22.3%
```

---

## 4. 间距系统

### 4.1 间距 Token

| Token | 值 | 用途 |
|-------|-----|------|
| `--space-1` | 4px | 图标与文字间距 |
| `--space-2` | 8px | 紧凑元素间距 |
| `--space-3` | 12px | 表格单元格内边距 |
| `--space-4` | 16px | 卡片内边距/标准间距 |
| `--space-5` | 20px | 卡片之间间距 |
| `--space-6` | 24px | 区块内边距 |
| `--space-8` | 32px | 区块之间间距 |
| `--space-10` | 40px | 大区块之间 |
| `--space-12` | 48px | 页面级间距 |

### 4.2 布局网格

```
页面最大宽度: 1440px
内容区域: 左右各 24px padding (移动端 16px)
卡片间距: 20px
卡片内边距: 24px
卡片圆角: 12px

响应式断点:
  Mobile:  < 768px   (单列)
  Tablet:  768-1024px (双列)
  Desktop: > 1024px   (多列弹性布局)
```

---

## 5. 组件规范

### 5.1 卡片 (Card)

```css
.card {
  background: var(--bg-card);             /* #111827 */
  border: 1px solid rgba(255,255,255,0.06);
  border-radius: 12px;
  padding: 24px;
  transition: all 200ms ease;
}

.card:hover {
  border-color: rgba(59,130,246,0.3);     /* primary 30% */
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
}
```

### 5.2 指数概览卡片

```css
.index-card {
  background: var(--bg-card);
  border-radius: 12px;
  padding: 16px 20px;
  min-width: 200px;
}

.index-card__name {
  font: 500 14px var(--font-ui);
  color: var(--text-secondary);
}

.index-card__price {
  font: 700 24px var(--font-data);
  color: var(--text-primary);
  margin: 4px 0;
}

.index-card__change--up {
  font: 600 16px var(--font-data);
  color: var(--color-up);                 /* 红色 */
}

.index-card__change--down {
  font: 600 16px var(--font-data);
  color: var(--color-down);               /* 绿色 */
}
```

### 5.3 推荐列表表格

```css
.rec-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.rec-table th {
  font: 500 12px var(--font-ui);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(255,255,255,0.06);
  text-align: left;
}

.rec-table td {
  font: 400 14px var(--font-data);
  color: var(--text-primary);
  padding: 16px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  cursor: pointer;
}

.rec-table tr:hover td {
  background: rgba(59,130,246,0.05);
}

/* 评分单元格 - 根据分值着色 */
.score-cell--high { color: var(--color-up); }       /* ≥80 */
.score-cell--mid  { color: var(--color-accent); }    /* 40-79 */
.score-cell--low  { color: var(--color-down); }      /* <40 */
```

### 5.4 评分徽章

```css
.score-badge {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: 20px;
  font: 600 14px var(--font-data);
}

.score-badge--bullish {
  background: rgba(239,68,68,0.15);
  color: #EF4444;
}

.score-badge--neutral {
  background: rgba(245,158,11,0.15);
  color: #F59E0B;
}

.score-badge--bearish {
  background: rgba(34,197,94,0.15);
  color: #22C55E;
}
```

### 5.5 信号标签

```css
.signal-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font: 400 12px var(--font-ui);
}

.signal-tag--bullish {
  background: rgba(239,68,68,0.1);
  color: #FCA5A5;
}

.signal-tag--bearish {
  background: rgba(34,197,94,0.1);
  color: #86EFAC;
}

.signal-tag--warning {
  background: rgba(245,158,11,0.1);
  color: #FDE68A;
}
```

### 5.6 按钮

```css
/* 主操作按钮 */
.btn-primary {
  background: var(--color-accent);        /* #F59E0B */
  color: #0B0F19;
  font: 600 14px var(--font-ui);
  padding: 10px 24px;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  transition: all 200ms ease;
}

.btn-primary:hover {
  background: #D97706;
  transform: translateY(-1px);
}

.btn-primary:active {
  transform: translateY(0);
}

/* 次要按钮 */
.btn-secondary {
  background: transparent;
  color: var(--color-primary);
  border: 1px solid var(--color-primary);
  font: 500 14px var(--font-ui);
  padding: 10px 24px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 200ms ease;
}

.btn-secondary:hover {
  background: rgba(59,130,246,0.1);
}
```

### 5.7 导航栏

```css
.navbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 56px;
  background: rgba(11,15,25,0.85);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid rgba(255,255,255,0.06);
  z-index: 50;
  display: flex;
  align-items: center;
  padding: 0 24px;
}

.navbar__logo {
  font: 700 18px var(--font-ui);
  color: var(--color-primary);
}

.navbar__date {
  font: 400 14px var(--font-data);
  color: var(--text-muted);
  margin-left: auto;
}
```

---

## 6. 图表视觉规范

### 6.1 ECharts 全局主题

```javascript
const CHART_THEME = {
  backgroundColor: 'transparent',
  textStyle: {
    fontFamily: "'Fira Sans', 'PingFang SC', sans-serif",
    color: '#94A3B8'
  },
  title: {
    textStyle: {
      fontFamily: "'Fira Sans', 'PingFang SC', sans-serif",
      color: '#F1F5F9',
      fontSize: 16,
      fontWeight: 600
    }
  },
  legend: {
    textStyle: { color: '#94A3B8', fontSize: 12 }
  },
  tooltip: {
    backgroundColor: '#1F2937',
    borderColor: 'rgba(255,255,255,0.1)',
    textStyle: {
      color: '#F1F5F9',
      fontFamily: "'Fira Code', monospace",
      fontSize: 13
    }
  },
  xAxis: {
    axisLine: { lineStyle: { color: '#374151' } },
    axisLabel: { color: '#64748B', fontSize: 11 },
    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }
  },
  yAxis: {
    axisLine: { lineStyle: { color: '#374151' } },
    axisLabel: {
      color: '#64748B',
      fontSize: 11,
      fontFamily: "'Fira Code', monospace"
    },
    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.04)' } }
  }
};
```

### 6.2 K线图规范

```javascript
// Lightweight Charts 配置
const KLINE_OPTIONS = {
  layout: {
    background: { color: '#111827' },
    textColor: '#94A3B8',
    fontSize: 12,
    fontFamily: "'Fira Code', monospace"
  },
  grid: {
    vertLines: { color: 'rgba(255,255,255,0.04)' },
    horzLines: { color: 'rgba(255,255,255,0.04)' }
  },
  crosshair: {
    mode: 0,       // Normal crosshair
    vertLine: {
      color: 'rgba(59,130,246,0.4)',
      labelBackgroundColor: '#3B82F6'
    },
    horzLine: {
      color: 'rgba(59,130,246,0.4)',
      labelBackgroundColor: '#3B82F6'
    }
  },
  // A股红涨绿跌
  upColor: '#EF4444',
  downColor: '#22C55E',
  wickUpColor: '#EF4444',
  wickDownColor: '#22C55E',
  borderUpColor: '#EF4444',
  borderDownColor: '#22C55E'
};

// 均线颜色
const MA_COLORS = {
  MA5:   '#F59E0B',  // 琥珀 - 5日线
  MA10:  '#3B82F6',  // 蓝色 - 10日线
  MA20:  '#A855F7',  // 紫色 - 20日线
  MA60:  '#06B6D4',  // 青色 - 60日线
  MA120: '#F97316',  // 橙色 - 120日线
  MA250: '#EC4899',  // 粉色 - 250日线(年线)
};

// BOLL 通道
const BOLL_COLORS = {
  upper: 'rgba(245,158,11,0.6)',     // 上轨-琥珀半透明
  mid:   'rgba(59,130,246,0.6)',     // 中轨-蓝色半透明
  lower: 'rgba(245,158,11,0.6)',     // 下轨-琥珀半透明
  fill:  'rgba(245,158,11,0.05)'    // 通道填充-极淡琥珀
};
```

### 6.3 MACD 副图

```javascript
const MACD_CONFIG = {
  dif_color: '#3B82F6',         // DIF线 - 蓝色
  dea_color: '#F59E0B',         // DEA线 - 琥珀色
  histogram: {
    positive: '#EF4444',         // 红柱 (DIF>DEA)
    negative: '#22C55E',         // 绿柱 (DIF<DEA)
    positive_shrink: '#7F1D1D',  // 红柱缩短
    negative_shrink: '#14532D'   // 绿柱缩短
  }
};
```

### 6.4 热力图(板块)

```javascript
// ECharts Treemap 热力图
const HEATMAP_CONFIG = {
  type: 'treemap',
  breadcrumb: { show: false },
  itemStyle: {
    borderColor: '#0B0F19',
    borderWidth: 2,
    gapWidth: 2
  },
  label: {
    fontFamily: "'Fira Sans', 'PingFang SC', sans-serif",
    fontSize: 13,
    color: '#F1F5F9'
  },
  // 涨跌幅映射颜色
  visualMap: {
    min: -7,
    max: 7,
    inRange: {
      color: [
        '#4ADE80',  // -7% 最亮绿
        '#22C55E',  // -5%
        '#16A34A',  // -3%
        '#166534',  // -1%
        '#374151',  //  0% 灰色
        '#7F1D1D',  // +1%
        '#B91C1C',  // +3%
        '#DC2626',  // +5%
        '#EF4444'   // +7% 最亮红
      ]
    }
  }
};
```

### 6.5 桑基图(资金流向)

```javascript
const SANKEY_CONFIG = {
  type: 'sankey',
  nodeWidth: 20,
  nodeGap: 12,
  orient: 'horizontal',
  label: {
    color: '#F1F5F9',
    fontFamily: "'Fira Sans', 'PingFang SC', sans-serif",
    fontSize: 12
  },
  lineStyle: {
    curveness: 0.5,
    opacity: 0.3
  },
  emphasis: {
    lineStyle: { opacity: 0.6 }
  },
  // 节点颜色: 资金来源为蓝色系，板块为行情色
  nodeColors: {
    north_fund: '#3B82F6',     // 北向资金 - 蓝
    main_fund: '#F59E0B',      // 主力资金 - 琥珀
    retail_fund: '#94A3B8',    // 散户资金 - 灰
    sector_up: '#EF4444',      // 上涨板块 - 红
    sector_down: '#22C55E'     // 下跌板块 - 绿
  }
};
```

### 6.6 雷达图(评分)

```javascript
const RADAR_CONFIG = {
  radar: {
    indicator: [
      { name: '技术面', max: 100 },
      { name: '基本面', max: 100 },
      { name: '资金面', max: 100 },
      { name: '情绪面', max: 100 },
      { name: '行业', max: 100 }
    ],
    axisLine: { lineStyle: { color: 'rgba(255,255,255,0.1)' } },
    splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } },
    splitArea: { areaStyle: { color: ['transparent'] } },
    name: {
      color: '#94A3B8',
      fontFamily: "'Fira Sans', 'PingFang SC', sans-serif"
    }
  },
  series: {
    areaStyle: {
      color: 'rgba(59,130,246,0.2)'
    },
    lineStyle: {
      color: '#3B82F6',
      width: 2
    },
    itemStyle: {
      color: '#3B82F6'
    }
  }
};
```

---

## 7. 交互规范

### 7.1 过渡动画

| 场景 | 时长 | 缓动 | 属性 |
|------|------|------|------|
| 按钮悬浮 | 200ms | ease | background, transform |
| 卡片悬浮 | 200ms | ease | border-color, box-shadow |
| 表格行悬浮 | 150ms | ease | background |
| 页面切换 | 300ms | ease-out | opacity, transform |
| 图表加载 | 500ms | ease-out | ECharts animation |
| 数字变化 | 300ms | ease-out | CSS counter / JS tween |
| Tooltip 显示 | 100ms | ease-out | opacity |
| Tooltip 隐藏 | 150ms | ease-in | opacity |

### 7.2 加载状态

```css
/* 骨架屏 - 卡片 */
.skeleton-card {
  background: var(--bg-card);
  border-radius: 12px;
  overflow: hidden;
}

.skeleton-line {
  height: 16px;
  background: linear-gradient(
    90deg,
    rgba(255,255,255,0.04) 25%,
    rgba(255,255,255,0.08) 50%,
    rgba(255,255,255,0.04) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
  margin-bottom: 8px;
}

@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

### 7.3 空状态

```
非交易日/数据未生成:
┌────────────────────────────┐
│                            │
│     [Chart Icon - SVG]     │
│                            │
│   今日暂无推荐数据          │
│   下一交易日数据将于         │
│   收盘后自动生成            │
│                            │
│   [查看历史推荐]            │
│                            │
└────────────────────────────┘
```

### 7.4 错误状态

```
数据采集失败:
┌────────────────────────────┐
│  ⚠ 部分数据采集异常         │
│  资金流数据获取失败，        │
│  已使用昨日缓存数据         │
│  最后更新: 16:32            │
│                [重新采集]   │
└────────────────────────────┘
```

---

## 8. 响应式布局

### 8.1 断点定义

| 断点 | 宽度 | 布局 |
|------|------|------|
| Mobile | <768px | 单列堆叠 |
| Tablet | 768-1024px | 双列网格 |
| Desktop | 1024-1440px | 多列弹性 |
| Wide | >1440px | 居中最大1440px |

### 8.2 主看板布局

```
Desktop (>1024px):
┌──────────────────────────────────┐
│ [指数卡1] [指数卡2] [指数卡3] [指数卡4] │  ← 4列
├──────────────────┬───────────────┤
│   热力图 (60%)    │ 桑基图 (40%)  │  ← 2列
├──────────────────┴───────────────┤
│        推荐列表 (100%)           │  ← 全宽表格
├──────────────────────────────────┤
│        情绪仪表盘 (100%)         │  ← 全宽
└──────────────────────────────────┘

Mobile (<768px):
┌────────────────┐
│ [指数1] [指数2] │  ← 2列滑动
├────────────────┤
│    热力图       │  ← 全宽
├────────────────┤
│    桑基图       │  ← 全宽
├────────────────┤
│  推荐列表(卡片) │  ← 转为卡片列表
├────────────────┤
│   情绪仪表盘    │  ← 全宽
└────────────────┘
```

### 8.3 移动端适配要点

- 推荐列表在移动端转为卡片列表（非表格）
- K线图支持手势缩放和滑动
- 图表高度自适应，最小高度300px
- 导航栏固定顶部，56px高度
- 内容区域 padding-top: 72px (导航高度+间距)

---

## 9. 图标规范

### 9.1 图标库

使用 **Lucide Icons** (SVG)，不使用 emoji 作为界面图标。

### 9.2 常用图标映射

| 用途 | Lucide 图标名 | 场景 |
|------|--------------|------|
| 涨幅 | `trending-up` | 涨幅指示 |
| 跌幅 | `trending-down` | 跌幅指示 |
| 设置 | `settings` | 系统设置 |
| 刷新 | `refresh-cw` | 手动刷新 |
| 搜索 | `search` | 搜索股票 |
| 返回 | `arrow-left` | 返回上页 |
| 日历 | `calendar` | 日期选择 |
| 警告 | `alert-triangle` | 风险提示 |
| 信息 | `info` | 工具提示 |
| 图表 | `bar-chart-2` | 图表切换 |
| 列表 | `list` | 列表视图 |
| 时钟 | `clock` | 最后更新时间 |

### 9.3 图标尺寸

| 场景 | 尺寸 | 线宽 |
|------|------|------|
| 导航图标 | 20px | 1.5px |
| 内联图标 | 16px | 1.5px |
| 状态图标 | 14px | 2px |
| 装饰图标 | 24px | 1.5px |

---

## 10. 无障碍 & 性能

### 10.1 无障碍要求

| 要求 | 实现方式 |
|------|---------|
| 颜色对比度 | 主文字 #F1F5F9 on #0B0F19 = 15.4:1 (Pass AAA) |
| 次文字对比度 | #94A3B8 on #0B0F19 = 7.1:1 (Pass AA) |
| 键盘导航 | Tab 顺序合理，焦点样式可见 |
| 减少动画 | 尊重 `prefers-reduced-motion` |
| 图表替代 | 热力图/桑基图提供数据表格备选 |
| 语义化 | 使用合适的 HTML 标签 (table, nav, main, section) |

### 10.2 焦点样式

```css
:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
  border-radius: 4px;
}
```

### 10.3 性能要求

| 指标 | 目标 |
|------|------|
| 首屏加载 (FCP) | < 1.5s |
| 图表渲染 | < 500ms |
| 页面切换 | < 300ms |
| 图片格式 | WebP + lazy loading |
| 字体加载 | font-display: swap |
| JS 大小 | ECharts 按需引入，减少bundle |

---

## 11. 合规提示组件

### 11.1 页面底部固定提示

```css
.disclaimer-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 36px;
  background: rgba(245,158,11,0.1);
  border-top: 1px solid rgba(245,158,11,0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 40;
}

.disclaimer-bar__text {
  font: 400 12px var(--font-ui);
  color: #FDE68A;
  letter-spacing: 0.02em;
}
```

**文案**: "投资有风险，入市需谨慎。本系统仅供学习研究参考，不构成任何投资建议。"

---

## 12. CSS 变量汇总

```css
:root {
  /* 背景 */
  --bg-primary: #0B0F19;
  --bg-card: #111827;
  --bg-elevated: #1F2937;
  --bg-input: #1A2332;

  /* 文字 */
  --text-primary: #F1F5F9;
  --text-secondary: #94A3B8;
  --text-muted: #64748B;
  --text-disabled: #475569;

  /* 行情色 (A股: 红涨绿跌) */
  --color-up: #EF4444;
  --color-up-light: #FCA5A5;
  --color-up-dark: #991B1B;
  --color-down: #22C55E;
  --color-down-light: #86EFAC;
  --color-down-dark: #166534;
  --color-flat: #F8FAFC;

  /* 功能色 */
  --color-primary: #3B82F6;
  --color-primary-light: #60A5FA;
  --color-primary-dark: #1E40AF;
  --color-accent: #F59E0B;
  --color-warning: #F97316;
  --color-info: #06B6D4;

  /* 字体 */
  --font-data: 'Fira Code', 'SF Mono', monospace;
  --font-ui: 'Fira Sans', 'PingFang SC', 'Microsoft YaHei', system-ui, sans-serif;

  /* 间距 */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;

  /* 圆角 */
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --radius-xl: 16px;
  --radius-full: 9999px;

  /* 阴影 */
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.3);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.4);
  --shadow-lg: 0 10px 24px rgba(0,0,0,0.5);
  --shadow-xl: 0 20px 40px rgba(0,0,0,0.6);

  /* 边框 */
  --border-subtle: rgba(255,255,255,0.06);
  --border-default: rgba(255,255,255,0.1);
  --border-strong: rgba(255,255,255,0.2);

  /* 过渡 */
  --transition-fast: 150ms ease;
  --transition-normal: 200ms ease;
  --transition-slow: 300ms ease-out;

  /* Z-index 层级 */
  --z-base: 0;
  --z-card: 10;
  --z-dropdown: 20;
  --z-sticky: 30;
  --z-navbar: 40;
  --z-disclaimer: 40;
  --z-modal: 50;
  --z-tooltip: 60;
}
```

---

*文档结束 | A股智选 UI/UX 规范 v1.0 | 2026-02-20*
