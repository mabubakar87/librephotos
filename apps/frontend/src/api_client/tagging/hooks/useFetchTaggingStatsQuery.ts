import { useQuery } from "@tanstack/react-query";
import { z } from "zod";
import { parseWithNotification } from "../../../util/zodUtils";
import { fetchClient } from "../../api";

const TaggingStatRow = z.object({
  key: z.string(),
  count: z.number(),
  percent: z.number(),
});

const TaggingStatsResponse = z.object({
  total_photos: z.number(),
  tagging: z.array(TaggingStatRow),
  captions: z.array(TaggingStatRow),
  untagged_scene: z.number(),
  untagged_scene_percent: z.number(),
});

export type TaggingStats = z.infer<typeof TaggingStatsResponse>;

export const TaggingStatsQueryKeys = ["taggingStats"];

export const useFetchTaggingStatsQuery = () =>
  useQuery({
    queryKey: [...TaggingStatsQueryKeys],
    queryFn: async () => {
      const response = await fetchClient.get("/tagging/stats");
      return parseWithNotification(TaggingStatsResponse, response, "Failed to load tagging stats");
    },
  });
