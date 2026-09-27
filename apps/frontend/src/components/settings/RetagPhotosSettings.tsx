import {
  Button,
  Grid,
  Progress,
  Radio,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { IconTags as Tags } from "@tabler/icons-react";
import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useFetchTaggingStatsQuery, useRetagPhotosMutation } from "../../api_client/tagging/hooks";
import { useGetSettingsQuery } from "../../api_client/settings/hooks";

const TAGGING_MODELS = [
  { value: "mobileclip_s2", label: "MobileCLIP-S2 (fast)" },
  { value: "siglip2", label: "SigLIP 2 (accurate)" },
];

const CAPTION_LABELS: Record<string, string> = {
  im2txt: "im2txt (legacy caption)",
  moondream: "Moondream (visual LLM caption)",
  lfm2_vl_450m: "LFM2.5-VL caption",
  user_caption: "Manual caption",
};

const TAGGING_LABELS: Record<string, string> = {
  mobileclip_s2: "MobileCLIP-S2",
  siglip2: "SigLIP 2",
  places365: "Places365 (legacy)",
};

function labelForKey(key: string, kind: "tagging" | "caption") {
  if (kind === "tagging") {
    return TAGGING_LABELS[key] ?? key;
  }
  return CAPTION_LABELS[key] ?? key;
}

type RetagPhotosSettingsProps = {
  workerAvailable: boolean;
  onRequireWorker: () => void;
};

export function RetagPhotosSettings({ workerAvailable, onRequireWorker }: RetagPhotosSettingsProps) {
  const { t } = useTranslation();
  const { data: stats, isFetching } = useFetchTaggingStatsQuery();
  const { data: siteSettings } = useGetSettingsQuery();
  const retag = useRetagPhotosMutation();
  const [taggingModel, setTaggingModel] = useState(siteSettings?.tagging_model ?? "mobileclip_s2");
  const [mode, setMode] = useState<"missing_only" | "retag_all">("missing_only");
  const [directoryPrefix, setDirectoryPrefix] = useState("");

  const modelOptions = useMemo(() => TAGGING_MODELS, []);

  useEffect(() => {
    if (siteSettings?.tagging_model) {
      setTaggingModel(siteSettings.tagging_model);
    }
  }, [siteSettings?.tagging_model]);

  const startRetag = () => {
    if (!workerAvailable) {
      onRequireWorker();
      return;
    }
    retag.mutate({
      tagging_model: taggingModel,
      mode,
      directory_prefix: directoryPrefix.trim() || undefined,
    });
  };

  return (
    <Grid>
      <Grid.Col span={{ base: 12, sm: "auto" }}>
        <Stack gap={4}>
          <Text>{t("settings.retagPhotos.title")}</Text>
          <Text fz="sm" c="dimmed">
            {t("settings.retagPhotos.description")}
          </Text>
        </Stack>
      </Grid.Col>
      <Grid.Col span={12}>
        {isFetching && !stats ? (
          <Progress value={100} animated size="sm" />
        ) : stats ? (
          <Stack gap="xs">
            <Text fz="sm" fw={500}>
              {t("settings.retagPhotos.statsTotal", { count: stats.total_photos })}
            </Text>
            <Text fz="sm" c="dimmed">
              {t("settings.retagPhotos.untaggedScene", {
                count: stats.untagged_scene,
                percent: stats.untagged_scene_percent,
              })}
            </Text>
            {stats.tagging.length > 0 && (
              <Table fz="sm" striped withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("settings.retagPhotos.sceneTagging")}</Table.Th>
                    <Table.Th>{t("settings.retagPhotos.count")}</Table.Th>
                    <Table.Th>{t("settings.retagPhotos.percent")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {stats.tagging.map(row => (
                    <Table.Tr key={row.key}>
                      <Table.Td>{labelForKey(row.key, "tagging")}</Table.Td>
                      <Table.Td>{row.count}</Table.Td>
                      <Table.Td>{row.percent}%</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
            {stats.captions.length > 0 && (
              <Table fz="sm" striped withTableBorder>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("settings.retagPhotos.captions")}</Table.Th>
                    <Table.Th>{t("settings.retagPhotos.count")}</Table.Th>
                    <Table.Th>{t("settings.retagPhotos.percent")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {stats.captions.map(row => (
                    <Table.Tr key={row.key}>
                      <Table.Td>{labelForKey(row.key, "caption")}</Table.Td>
                      <Table.Td>{row.count}</Table.Td>
                      <Table.Td>{row.percent}%</Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            )}
          </Stack>
        ) : null}
      </Grid.Col>
      <Grid.Col span={{ base: 12, sm: 6 }}>
        <Select
          label={t("settings.retagPhotos.modelLabel")}
          description={t("settings.retagPhotos.modelDescription")}
          data={modelOptions}
          value={taggingModel}
          onChange={v => v && setTaggingModel(v)}
        />
      </Grid.Col>
      <Grid.Col span={{ base: 12, sm: 6 }}>
        <Radio.Group
          label={t("settings.retagPhotos.modeLabel")}
          value={mode}
          onChange={v => setMode(v as "missing_only" | "retag_all")}
        >
          <Stack gap={4} mt={4}>
            <Radio value="missing_only" label={t("settings.retagPhotos.modeMissing")} />
            <Radio value="retag_all" label={t("settings.retagPhotos.modeRetagAll")} />
          </Stack>
        </Radio.Group>
      </Grid.Col>
      <Grid.Col span={12}>
        <TextInput
          label={t("settings.retagPhotos.directoryLabel")}
          description={t("settings.retagPhotos.directoryDescription")}
          placeholder="09/dinner"
          value={directoryPrefix}
          onChange={e => setDirectoryPrefix(e.currentTarget.value)}
        />
      </Grid.Col>
      <Grid.Col span={{ base: 12, sm: "content" }}>
        <Button
          leftSection={<Tags size="1rem" />}
          onClick={startRetag}
          loading={retag.isPending}
          disabled={!workerAvailable}
        >
          {t("settings.retagPhotos.start")}
        </Button>
      </Grid.Col>
    </Grid>
  );
}
