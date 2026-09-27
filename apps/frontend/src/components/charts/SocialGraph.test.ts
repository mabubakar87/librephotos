import { describe, expect, it } from "vitest";
import { filterSocialGraphByMinWeight, linkColorForWeight } from "./SocialGraph";

describe("filterSocialGraphByMinWeight", () => {
  const sample = {
    nodes: [
      { id: "Alice", photo_count: 5 },
      { id: "Bob", photo_count: 3 },
      { id: "Carol", photo_count: 2 },
    ],
    links: [
      { source: "Alice", target: "Bob", weight: 2 },
      { source: "Bob", target: "Carol", weight: 10 },
    ],
  };

  it("keeps all data when min weight is 1", () => {
    expect(filterSocialGraphByMinWeight(sample, 1)).toEqual(sample);
  });

  it("drops weak links and isolated nodes", () => {
    const result = filterSocialGraphByMinWeight(sample, 5);
    expect(result.links).toEqual([{ source: "Bob", target: "Carol", weight: 10 }]);
    expect(result.nodes.map(n => n.id).sort()).toEqual(["Bob", "Carol"]);
  });
});

describe("linkColorForWeight", () => {
  it("maps fixed tiers", () => {
    expect(linkColorForWeight(1)).toBe("#868e96");
    expect(linkColorForWeight(50)).toBe("#12939A");
    expect(linkColorForWeight(200)).toBe("#1971c2");
    expect(linkColorForWeight(800)).toBe("#e03131");
  });
});
