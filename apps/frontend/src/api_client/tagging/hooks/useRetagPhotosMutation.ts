import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { notification } from "../../../service/notifications";
import { parseWithNotification } from "../../../util/zodUtils";
import { fetchClient, queryClient } from "../../api";
import { ThingsAlbumsQueryKeys } from "../../albums/hooks/useFetchThingsAlbumsQuery";
import { JobsQueryKeys } from "../../jobs/hooks/useJobsQuery";
import { WorkerQueryKeys } from "../../jobs/hooks/useWorkerQuery";
import { TaggingStatsQueryKeys } from "./useFetchTaggingStatsQuery";

const JobResponse = z.object({
  status: z.boolean(),
  job_id: z.string(),
});

export type RetagPhotosRequest = {
  tagging_model: string;
  mode: "missing_only" | "retag_all";
  directory_prefix?: string;
};

export const useRetagPhotosMutation = () =>
  useMutation({
    mutationFn: async (body: RetagPhotosRequest) => {
      const response = await fetchClient.post("/retagphotos/", body);
      return parseWithNotification(JobResponse, response, "Failed to start retag job");
    },
    onSuccess: () => {
      notification.startRetagPhotos();
      queryClient.invalidateQueries({ queryKey: [...TaggingStatsQueryKeys] });
      queryClient.invalidateQueries({ queryKey: [...ThingsAlbumsQueryKeys] });
      queryClient.invalidateQueries({ queryKey: [...JobsQueryKeys] });
      queryClient.invalidateQueries({ queryKey: [...WorkerQueryKeys] });
    },
  });
