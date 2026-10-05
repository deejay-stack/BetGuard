export type Classification = 'gambling' | 'non_gambling' | 'unknown';
export type ClassificationSource = 'reviewed_catalog' | 'model' | 'unavailable';
type BaseResult = {
  hostname: string;
  explanation: string;
};
export type CatalogResult = BaseResult &
  (
    | {
        source: 'reviewed_catalog';
        classification: Classification;
        reason: 'reviewed_catalog';
        label_provenance: string;
        reviewed_at: string;
        model_version?: null;
        calibrated_probability?: null;
      }
    | {
        source: 'unavailable';
        classification: 'unknown';
        reason: 'not_in_catalog' | 'not_reviewed';
        label_provenance?: null;
        reviewed_at?: null;
        model_version?: null;
        calibrated_probability?: null;
      }
    | ({
        source: 'model';
        model_version: string;
        label_provenance?: null;
        reviewed_at?: null;
        calibrated_probability?: number | null;
      } & (
        | {
            classification: 'gambling' | 'non_gambling';
            reason: 'model_prediction';
          }
        | {
            classification: 'unknown';
            reason: 'model_abstained' | 'model_ineligible';
          }
      ))
  );
