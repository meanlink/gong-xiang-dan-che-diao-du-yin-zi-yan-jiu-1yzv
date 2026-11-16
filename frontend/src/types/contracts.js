/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
/** @typedef {{id:number,name:string,status:string,dataset_id:number,result_dataset_id:number|null,progress:{total:number,resolved:number,disputed:number,collecting:number,waiting:number,open_claims:number,overdue_claims:number,ready:boolean}}} Review */
/** @typedef {{id:number,idx:number,record:Object,status:string,opinion:string|null,rationale:string,claimed_at:number,due_at:number,submitted_at:number|null}} ReviewAssignmentView */
export {};
