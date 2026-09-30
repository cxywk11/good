import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Button, Form, Input, Segmented } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { api, setSession, clearSession, SessionData } from './api';
import { PageTitle } from './ui';
export default function Auth(){
 const [mode,setMode]=useState('登录'),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false);
 const navigate=useNavigate(),cache=useQueryClient();
 async function submit(values:{email:string;password:string}){setBusy(true);setError('');try{
  if(mode==='注册'){await api('/auth/register',{method:'POST',body:JSON.stringify(values)});setNotice('注册成功，请登录。');setMode('登录')}
  else{const result=await api<SessionData>('/auth/login',{method:'POST',body:JSON.stringify(values)});setSession(result);cache.clear();navigate('/')}
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function logout(){try{await api('/auth/logout',{method:'POST'});clearSession();cache.clear();setNotice('已退出登录')}catch(e){setError((e as Error).message)}}
 return <><PageTitle eyebrow="ACCOUNT" title="账户" description="注册账户，或登录后使用研究与管理功能。"/><div className="panel content-pad auth-card"><Segmented block options={['登录','注册']} value={mode} onChange={setMode}/><div className="section-gap">{notice&&<Alert type="success" message={notice}/>} {error&&<Alert type="error" message={error}/>}<Form layout="vertical" onFinish={submit}><Form.Item label="邮箱" name="email" rules={[{required:true,type:'email'}]}><Input autoComplete="username"/></Form.Item><Form.Item label="密码" name="password" rules={[{required:true,min:12,max:128,message:'密码长度须为 12–128 个字符'}]}><Input.Password autoComplete={mode==='登录'?'current-password':'new-password'}/></Form.Item><Button htmlType="submit" type="primary" block loading={busy}>{mode}</Button></Form><Button className="section-gap" block onClick={()=>void logout()}>退出当前会话</Button><p className="muted">新注册账户为 USER。管理员通过部署配置初始化。</p></div></div></>;
}
