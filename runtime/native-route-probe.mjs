// One tiny transport diagnostic; never a benchmark or retry of a task.
import { writeFileSync } from "node:fs";
import { completeSimple } from "/opt/benchflow/pi/node_modules/@earendil-works/pi-ai/dist/compat.js";
const model = {id:"openai/gpt-5.4-mini",name:"GPT-5.4 mini",provider:"openrouter",api:"openai-completions",
  baseUrl:"https://openrouter.ai/api/v1",reasoning:true,input:["text"],contextWindow:400000,maxTokens:128000,
  cost:{input:.75,output:4.5,cacheRead:.075,cacheWrite:0},
  compat:{thinkingFormat:"openai",supportsReasoningEffort:true,maxTokensField:"max_completion_tokens"}};
let transport = 0, httpStatus = null;
const result = await completeSimple(model,{messages:[{role:"user",content:"Reply only OK.",timestamp:Date.now()}]},
  {apiKey:process.env.OPENROUTER_API_KEY,reasoning:"medium",maxTokens:64,maxRetries:0,signal:AbortSignal.timeout(60000),
    fetch:async (...args)=>{transport++;const response=await fetch(...args);httpStatus=response.status;return response;}});
const safe = {kind:"native_pi_route_availability_not_benchmark",status:result.stopReason,http_status:httpStatus,
  transport_requests:transport,response_id:result.responseId,usage:result.usage,
  error_message:result.errorMessage?.replaceAll(process.env.OPENROUTER_API_KEY,"[REDACTED]").slice(0,1500)};
writeFileSync('/out/result.json',JSON.stringify(safe,null,2)+'\n');
console.log(JSON.stringify(safe));
