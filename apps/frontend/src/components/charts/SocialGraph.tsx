import { Group, Loader, Paper, Select, Slider, Stack, Text, useComputedColorScheme } from "@mantine/core";
import { IconShare } from "@tabler/icons-react";
import { drag } from "d3-drag";
import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation } from "d3-force";
import { select } from "d3-selection";
import { zoom as d3Zoom } from "d3-zoom";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useDimensions from "react-cool-dimensions";
import { useTranslation } from "react-i18next";
import { useFetchSocialGraphQuery, type PersonDataPointList } from "../../api_client/stats/hooks";
import { EmptyState } from "../common/EmptyState";

type Props = Readonly<{
  height: number;
}>;

type GraphNode = PersonDataPointList["nodes"][number] & { x?: number; y?: number; fx?: number | null; fy?: number | null };
type GraphLink = PersonDataPointList["links"][number];

type GraphTooltip = Readonly<{
  text: string;
  x: number;
  y: number;
}>;

const MIN_NODE_R = 8;
const MAX_NODE_R = 28;
const MIN_LINK_WIDTH = 1;
const MAX_LINK_WIDTH = 6;

const SLIDER_MARKS = [
  { value: 1, label: "1" },
  { value: 10, label: "10" },
  { value: 100, label: "100" },
  { value: 500, label: "500" },
  { value: 1500, label: "1500" },
];

/** Shared distinct photos — fixed tiers so large libraries stay readable. */
export const SOCIAL_GRAPH_LINK_COLORS = {
  strong: "#e03131",
  close: "#1971c2",
  regular: "#12939A",
  occasional: "#868e96",
} as const;

export function linkColorForWeight(weight: number): string {
  if (weight >= 500) return SOCIAL_GRAPH_LINK_COLORS.strong;
  if (weight >= 100) return SOCIAL_GRAPH_LINK_COLORS.close;
  if (weight >= 10) return SOCIAL_GRAPH_LINK_COLORS.regular;
  return SOCIAL_GRAPH_LINK_COLORS.occasional;
}

export function filterSocialGraphByMinWeight(data: PersonDataPointList, minWeight: number): PersonDataPointList {
  const links = data.links.filter(link => link.weight >= minWeight);
  const nodeIds = new Set<string>();
  for (const link of links) {
    nodeIds.add(link.source);
    nodeIds.add(link.target);
  }
  const nodes = data.nodes.filter(node => nodeIds.has(node.id));
  return { nodes, links };
}

function linkEndpointIds(link: GraphLink): [string, string] {
  const sourceId = typeof link.source === "object" ? (link.source as GraphNode).id : link.source;
  const targetId = typeof link.target === "object" ? (link.target as GraphNode).id : link.target;
  return [sourceId, targetId];
}

function scaleBetween(value: number, minIn: number, maxIn: number, minOut: number, maxOut: number) {
  if (maxIn <= minIn) {
    return (minOut + maxOut) / 2;
  }
  const t = (Math.sqrt(value) - Math.sqrt(minIn)) / (Math.sqrt(maxIn) - Math.sqrt(minIn));
  return minOut + t * (maxOut - minOut);
}

function ForceGraph({
  data,
  width,
  height,
  focusPersonId,
  onTooltip,
}: {
  data: PersonDataPointList;
  width: number;
  height: number;
  focusPersonId: string | null;
  onTooltip: (tooltip: GraphTooltip | null) => void;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const colorScheme = useComputedColorScheme();
  const { t } = useTranslation();
  const setTooltipFromEvent = useCallback(
    (text: string, event: MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const rect = container.getBoundingClientRect();
      onTooltip({
        text,
        x: event.clientX - rect.left + 12,
        y: event.clientY - rect.top + 12,
      });
    },
    [onTooltip]
  );

  const renderGraph = useCallback(() => {
    if (!svgRef.current || !data || width <= 0 || height <= 0) return undefined;

    const svg = select(svgRef.current);
    svg.selectAll("*").remove();

    const g = svg.append("g");

    const zoom = d3Zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .on("zoom", event => {
        g.attr("transform", event.transform);
      });

    svg.call(zoom);

    const photoCounts = data.nodes.map(n => n.photo_count);
    const minPhotos = Math.min(...photoCounts);
    const maxPhotos = Math.max(...photoCounts);
    const weights = data.links.map(l => l.weight);
    const minWeight = weights.length ? Math.min(...weights) : 1;
    const maxWeight = weights.length ? Math.max(...weights) : 1;

    const nodeRadius = (d: GraphNode) =>
      scaleBetween(d.photo_count, minPhotos, maxPhotos, MIN_NODE_R, MAX_NODE_R);

    const linkWidth = (d: GraphLink) =>
      scaleBetween(d.weight, minWeight, maxWeight, MIN_LINK_WIDTH, MAX_LINK_WIDTH);

    const nodes: GraphNode[] = data.nodes.map(d => ({
      ...d,
      x: d.x ?? width / 2 + (Math.random() - 0.5) * 80,
      y: d.y ?? height / 2 + (Math.random() - 0.5) * 80,
    }));
    const links: GraphLink[] = data.links.map(d => ({ ...d }));

    const simulation = forceSimulation(nodes)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(links)
          .id(d => d.id)
          .distance(d => 70 + 90 / Math.sqrt(d.weight ?? 1))
      )
      .force("charge", forceManyBody<GraphNode>().strength(-520))
      .force("center", forceCenter(width / 2, height / 2))
      .force(
        "collision",
        forceCollide<GraphNode>().radius(d => nodeRadius(d) + 6)
      );

    const link = g
      .append("g")
      .selectAll("line")
      .data(links)
      .join("line")
      .attr("stroke", d => linkColorForWeight(d.weight))
      .attr("stroke-width", d => linkWidth(d))
      .attr("stroke-opacity", 0.55)
      .style("cursor", "pointer");

    const node = g
      .append("g")
      .selectAll("circle")
      .data(nodes)
      .join("circle")
      .attr("r", d => nodeRadius(d))
      .attr("fill", "lightblue")
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5)
      .style("cursor", "pointer")
      .call(
        drag<SVGCircleElement, GraphNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            /* eslint-disable no-param-reassign -- d3-force requires mutating node properties */
            d.fx = d.x;
            d.fy = d.y;
            /* eslint-enable no-param-reassign */
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          })
      );

    const label = g
      .append("g")
      .selectAll("text")
      .data(nodes)
      .join("text")
      .text(d => d.id)
      .attr("font-size", 10)
      .attr("font-weight", 600)
      .attr("fill", colorScheme === "dark" ? "white" : "black")
      .attr("text-anchor", "middle")
      .attr("dy", d => -(nodeRadius(d) + 6))
      .style("pointer-events", "none")
      .style("opacity", 0.92);

    const resetHighlight = () => {
      node.attr("stroke", "#fff").attr("stroke-width", 1.5).style("opacity", 1);
      link
        .attr("stroke", d => linkColorForWeight(d.weight))
        .attr("stroke-opacity", 0.55)
        .attr("stroke-width", d => linkWidth(d))
        .style("opacity", 1);
      label
        .attr("font-size", 10)
        .attr("fill", colorScheme === "dark" ? "white" : "black")
        .style("opacity", 0.92);
    };

    const applyPersonFocus = (personId: string) => {
      const neighborIds = new Set<string>([personId]);
      for (const graphLink of links) {
        const [sourceId, targetId] = linkEndpointIds(graphLink);
        if (sourceId === personId) neighborIds.add(targetId);
        if (targetId === personId) neighborIds.add(sourceId);
      }

      node
        .attr("stroke", n => (n.id === personId ? "orange" : "#fff"))
        .attr("stroke-width", n => (n.id === personId ? 3 : 1.5))
        .style("opacity", n => (neighborIds.has(n.id) ? 1 : 0.12));
      link
        .attr("stroke-opacity", l => {
          const [sourceId, targetId] = linkEndpointIds(l);
          return sourceId === personId || targetId === personId ? 0.95 : 0.06;
        })
        .attr("stroke-width", l => {
          const [sourceId, targetId] = linkEndpointIds(l);
          return sourceId === personId || targetId === personId ? linkWidth(l) + 1.5 : linkWidth(l);
        })
        .style("opacity", l => {
          const [sourceId, targetId] = linkEndpointIds(l);
          return sourceId === personId || targetId === personId ? 1 : 0.15;
        });
      label
        .attr("font-size", n => (n.id === personId ? 12 : 10))
        .attr("fill", n => (n.id === personId ? "orange" : colorScheme === "dark" ? "white" : "black"))
        .style("opacity", n => (neighborIds.has(n.id) ? (n.id === personId ? 1 : 0.92) : 0.15));
    };

    const applyDefaultVisualState = () => {
      if (focusPersonId) applyPersonFocus(focusPersonId);
      else resetHighlight();
    };

    const highlightHoverNode = (d: GraphNode, event: MouseEvent) => {
      setTooltipFromEvent(
        t("socialgraphtooltip.person", { name: d.id, count: d.photo_count }),
        event
      );
      node
        .attr("stroke", n => (n.id === d.id ? "orange" : "#fff"))
        .attr("stroke-width", n => (n.id === d.id ? 3 : 1.5));
      link
        .attr("stroke-opacity", l => {
          const [sourceId, targetId] = linkEndpointIds(l);
          return sourceId === d.id || targetId === d.id ? 0.95 : focusPersonId ? 0.06 : 0.12;
        })
        .attr("stroke-width", l => {
          const [sourceId, targetId] = linkEndpointIds(l);
          return sourceId === d.id || targetId === d.id ? linkWidth(l) + 1.5 : linkWidth(l);
        });
      label
        .attr("font-size", n => (n.id === d.id ? 12 : 10))
        .attr("fill", n => (n.id === d.id ? "orange" : colorScheme === "dark" ? "white" : "black"))
        .style("opacity", n => (n.id === d.id ? 1 : focusPersonId ? 0.15 : 0.55));
    };

    node
      .on("mouseover", (event, d) => highlightHoverNode(d, event))
      .on("mousemove", (event, d) => highlightHoverNode(d, event))
      .on("mouseout", () => {
        onTooltip(null);
        applyDefaultVisualState();
      });

    link
      .on("mouseover", (event, l) => {
        const [sourceId, targetId] = linkEndpointIds(l);
        setTooltipFromEvent(
          t("socialgraphtooltip.link", { nameA: sourceId, nameB: targetId, count: l.weight }),
          event
        );
        link.attr("stroke-opacity", row => (row === l ? 1 : 0.2)).attr("stroke-width", row => (row === l ? linkWidth(row) + 2 : linkWidth(row)));
      })
      .on("mousemove", (event, l) => {
        const [sourceId, targetId] = linkEndpointIds(l);
        setTooltipFromEvent(
          t("socialgraphtooltip.link", { nameA: sourceId, nameB: targetId, count: l.weight }),
          event
        );
      })
      .on("mouseout", () => {
        onTooltip(null);
        applyDefaultVisualState();
      });

    simulation.on("tick", () => {
      link
        .attr("x1", d => (d.source as GraphNode).x ?? 0)
        .attr("y1", d => (d.source as GraphNode).y ?? 0)
        .attr("x2", d => (d.target as GraphNode).x ?? 0)
        .attr("y2", d => (d.target as GraphNode).y ?? 0);
      node.attr("cx", d => d.x ?? 0).attr("cy", d => d.y ?? 0);
      label
        .attr("x", d => d.x ?? 0)
        .attr("y", d => d.y ?? 0)
        .attr("dy", d => -(nodeRadius(d) + 6));
    });

    applyDefaultVisualState();

    return () => {
      simulation.stop();
      onTooltip(null);
    };
  }, [colorScheme, data, focusPersonId, height, onTooltip, setTooltipFromEvent, t, width]);

  useEffect(() => {
    const cleanup = renderGraph();
    return () => cleanup?.();
  }, [renderGraph]);

  return (
    <div ref={containerRef} style={{ position: "relative", width: "100%" }}>
      <svg ref={svgRef} width={width} height={height} />
    </div>
  );
}

export function SocialGraph({ height }: Props) {
  const { data, isFetching, isSuccess } = useFetchSocialGraphQuery();
  const { observe: observeChange, width } = useDimensions({ onResize: ({ observe }) => observe() });
  const { t } = useTranslation();
  const [minWeight, setMinWeight] = useState(1);
  const [focusPersonId, setFocusPersonId] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<GraphTooltip | null>(null);

  const filteredData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    return filterSocialGraphByMinWeight(data, minWeight);
  }, [data, minWeight]);

  const personOptions = useMemo(() => {
    if (!data) return [];
    return [...data.nodes].sort((a, b) => a.id.localeCompare(b.id)).map(node => ({ value: node.id, label: node.id }));
  }, [data]);

  useEffect(() => {
    if (focusPersonId && !filteredData.nodes.some(node => node.id === focusPersonId)) {
      setFocusPersonId(null);
    }
  }, [filteredData.nodes, focusPersonId]);

  let graph: React.JSX.Element;
  if (isSuccess && data.nodes.length > 0) {
    if (filteredData.links.length === 0) {
      graph = (
        <Text size="sm" c="dimmed" mt="md">
          {t("socialgraphcontrols.noConnectionsAtThreshold")}
        </Text>
      );
    } else {
      graph = (
        <ForceGraph
          data={filteredData}
          width={width}
          height={height}
          focusPersonId={focusPersonId}
          onTooltip={setTooltip}
        />
      );
    }
  } else if (isFetching) {
    graph = (
      <Group>
        <Loader />
        <Text>{t("fetchingsocialgraph")}</Text>
      </Group>
    );
  } else {
    graph = (
      <EmptyState
        icon={<IconShare size={40} />}
        title={t("emptystate.socialgraph.title")}
        description={t("emptystate.socialgraph.description")}
        actionLabel={t("emptystate.goToFaces")}
        actionLink="/faces"
      />
    );
  }

  return (
    <div ref={observeChange} style={{ position: "relative" }}>
      {isSuccess && data.nodes.length > 0 ? (
        <Stack gap="xs" mb="sm">
          <SocialGraphControls
            minWeight={minWeight}
            onMinWeightChange={setMinWeight}
            focusPersonId={focusPersonId}
            onFocusPersonChange={setFocusPersonId}
            personOptions={personOptions}
            nodeCount={filteredData.nodes.length}
            linkCount={filteredData.links.length}
          />
          <SocialGraphLinkLegend />
        </Stack>
      ) : null}
      {graph}
      {tooltip ? (
        <Paper
          shadow="sm"
          p="xs"
          withBorder
          style={{
            position: "absolute",
            left: tooltip.x,
            top: tooltip.y,
            pointerEvents: "none",
            zIndex: 5,
            maxWidth: 320,
          }}
        >
          <Text size="xs">{tooltip.text}</Text>
        </Paper>
      ) : null}
    </div>
  );
}

type SocialGraphControlsProps = Readonly<{
  minWeight: number;
  onMinWeightChange: (value: number) => void;
  focusPersonId: string | null;
  onFocusPersonChange: (value: string | null) => void;
  personOptions: { value: string; label: string }[];
  nodeCount: number;
  linkCount: number;
}>;

function SocialGraphControls({
  minWeight,
  onMinWeightChange,
  focusPersonId,
  onFocusPersonChange,
  personOptions,
  nodeCount,
  linkCount,
}: SocialGraphControlsProps) {
  const { t } = useTranslation();

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="flex-end" wrap="wrap" gap="md">
        <Select
          label={t("socialgraphcontrols.highlightPerson")}
          placeholder={t("socialgraphcontrols.highlightPersonPlaceholder")}
          data={personOptions}
          value={focusPersonId}
          onChange={onFocusPersonChange}
          searchable
          clearable
          nothingFoundMessage={t("spotlight.nothingFound")}
          style={{ flex: "1 1 220px", maxWidth: 360 }}
        />
        <Text size="sm" c="dimmed">
          {t("socialgraphcontrols.summary", { nodes: nodeCount, links: linkCount })}
        </Text>
      </Group>
      <div>
        <Text size="sm" fw={500} mb={4}>
          {t("socialgraphcontrols.minSharedPhotos")}
        </Text>
        <Slider
          value={minWeight}
          onChange={onMinWeightChange}
          min={1}
          max={1500}
          step={1}
          marks={SLIDER_MARKS}
          label={value => String(value)}
          mb="lg"
        />
      </div>
    </Stack>
  );
}

function SocialGraphLinkLegend() {
  const { t } = useTranslation();
  const items = [
    { color: SOCIAL_GRAPH_LINK_COLORS.strong, label: t("socialgraphlinklegend.strong") },
    { color: SOCIAL_GRAPH_LINK_COLORS.close, label: t("socialgraphlinklegend.close") },
    { color: SOCIAL_GRAPH_LINK_COLORS.regular, label: t("socialgraphlinklegend.regular") },
    { color: SOCIAL_GRAPH_LINK_COLORS.occasional, label: t("socialgraphlinklegend.occasional") },
  ];

  return (
    <Group gap="md" wrap="wrap">
      <Text size="xs" c="dimmed">
        {t("socialgraphlinklegend.title")}
      </Text>
      {items.map(item => (
        <Group key={item.label} gap={6}>
          <svg width={28} height={8} aria-hidden>
            <line x1={0} y1={4} x2={28} y2={4} stroke={item.color} strokeWidth={3} strokeOpacity={0.85} />
          </svg>
          <Text size="xs">{item.label}</Text>
        </Group>
      ))}
    </Group>
  );
}
