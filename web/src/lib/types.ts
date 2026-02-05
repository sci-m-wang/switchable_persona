export type MediaUsed = {
  images?: string[];
  videos?: string[];
};

export type ExtractionRecord = {
  meta?: { post_id?: string };
  input?: { content?: string };
  result?: { extraction?: unknown; media_used?: MediaUsed };
};

export type NormalizedTask = {
  postId: string;
  content: string;
  extraction: unknown;
  media: MediaUsed;
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
  datasetInfo?: {
    source?: string;
    loadedAt: number;
    total: number;
  };
};
