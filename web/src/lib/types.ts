export type MediaUsed = {
  images?: string[];
  videos?: string[];
};

export type ExtractionRecord = {
  meta?: { post_id?: string };
  input?: {
    content?: string;
    article_url?: string;
    articleUrl?: string;
    video_url?: string;
    videoUrl?: string;
  };
  result?: { extraction?: unknown; media_used?: MediaUsed };
};

export type NormalizedTask = {
  postId: string;
  content: string;
  sourceUrl?: string;
  extraction: unknown;
  media: MediaUsed;
};

export type MediaResolveConfig = {
  mediaBaseUrl?: string;
  localWeiboPrefix?: string;
};

export type AnnotationEntry = {
  correct?: boolean;
  payload: unknown;
  updatedAt: number;
};

export type UserState = {
  annotatorId: string;
  consent: {
    agreed: boolean;
    signedName: string;
    signedAt?: number;
  };
  questionnaires: Record<string, Record<string, string>>;
  progressIndex: number;
  annotations: Record<string, AnnotationEntry>;
  mediaConfig?: MediaResolveConfig;
  datasetInfo?: {
    source?: string;
    loadedAt: number;
    total: number;
  };
};
